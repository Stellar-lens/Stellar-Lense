# Stellar Lense — Build Guide for Claude Code

Do these in order. Each step has a copy-paste prompt for Claude Code. Don't skip ahead — later prompts assume earlier steps are done, and Claude Code works best with one clear task at a time rather than everything at once.

## Step 0 — Get the two reference docs into the repo first

Before anything else, save these two files (already generated in this chat) into your new repo:
- `docs/PROJECT_PLAN.md` ← the project plan doc
- `docs/DESIGN_SYSTEM.md` ← the design tokens doc

Every prompt below tells Claude Code to read these first, so it's always working from the same spec instead of improvising.

```
mkdir -p stellar-lense/docs
# copy both files into stellar-lense/docs/ before continuing
```

---

## Step 1 — Initialize the monorepo skeleton

```
Read docs/PROJECT_PLAN.md in full before doing anything.

Set up the monorepo skeleton described in section 2 of that plan:
- apps/web, apps/api, apps/bot
- packages/core, packages/sdk-ts, packages/sdk-py, packages/ui
- contracts/soroban
- data/pipelines
- infra/helm, infra/monitoring, infra/ci
- docs/ (already has PROJECT_PLAN.md and DESIGN_SYSTEM.md)

Set up pnpm workspaces for the JS/TS packages, a Python workspace (pyproject.toml) for packages/core and apps/api, and confirm contracts/soroban will be its own Cargo workspace. Add a root Makefile with targets for lint-all and test-all. Don't migrate any actual repo content yet — just the skeleton, workspace configs, and a root README explaining the layout.
```

---

## Step 2 — Migrate each existing repo in, with history preserved

Run this once per repo (5 times total — core, contract, data, api, dashboard). Replace `<REPO_URL>` and `<TARGET_PATH>` each time using the mapping in the plan (§2).

```
Migrate the repo at <REPO_URL> into <TARGET_PATH> using git subtree (or git filter-repo if subtree runs into issues), preserving full commit history. After migrating, check that it doesn't break the workspace configs set up in Step 1 — adjust package.json/pyproject.toml paths as needed so it's recognized as a proper workspace member. Don't touch the dashboard repo's content yet — for that one, just land the raw files, we're replacing it entirely in a later step (skip if this run is the dashboard repo).
```

---

## Step 3 — Get everything building green before changing anything

```
Read docs/PROJECT_PLAN.md. Now that all repos are migrated into the monorepo, get every workspace member installing and building successfully in its new location. Run each package's existing test suite and report what passes/fails — don't fix failing tests yet, just give me a clear status report per package so we know what's actually broken vs. just needs config path updates.
```

---

## Step 4 — Rebrand pass

```
Read docs/PROJECT_PLAN.md section 3 (Rebrand Checklist). Run a full rebrand pass across the entire monorepo, renaming LedgerLens → Stellar Lense (confirmed spelling) everywhere: package names, env var prefixes (LEDGERLENS_* → STELLARLENSE_*), the Soroban contract name/symbol, API response headers, README/docs/CHANGELOG references, Docker/Helm chart names, and webhook payload field names. Go through the checklist item by item and report what you changed for each. Since this project was never publicly hosted, don't worry about backward-compatibility shims for external consumers.
```

---

## Step 5 — Scaffold the new website with the design system wired in

```
Read docs/DESIGN_SYSTEM.md in full. In apps/web, set up a Next.js app (TypeScript, Tailwind, App Router) if not already scaffolded, and wire in exactly what's specified in that doc: the three Google Fonts (Space Grotesk, IBM Plex Sans, IBM Plex Mono) via next/font, the CSS variables in globals.css, and the Tailwind config with the color/font tokens. Don't build any pages yet — just get the design system foundation in place and show me a blank page using the tokens correctly (background, text color, all three fonts rendering) so we can confirm it looks right before building real pages.
```

---

## Step 6 — Build the landing page

```
Read docs/DESIGN_SYSTEM.md and docs/PROJECT_PLAN.md. Build the marketing landing page for apps/web following the "Landing page" rules in the design system doc: Wegonorth-style layout — big split-screen headline, generous negative space, one deliberate animated moment on load, minimal bracketed nav. 

Ground the actual headline copy and content in what Stellar Lense does: wash-trading detection on the Stellar DEX (Benford's Law + ML ensemble + graph-based ring detection), publishing risk scores on-chain via Soroban. Write real copy specific to this product, not placeholder lorem ipsum or generic SaaS copy. Include sections for: hero, what it does, how detection works (brief, not overly technical), and a CTA into the app.
```

---

## Step 7 — Build the app/dashboard surfaces

```
Read docs/DESIGN_SYSTEM.md. Build the authenticated app routes in apps/web following the "App/dashboard" rules: dense, dark, DexScreener-style data tables — not CoinGecko-style cards. 

Pull the actual data shape from apps/api (check its existing endpoints from the migrated Ledegerlens-api repo) and build: an asset risk-ranking table, an individual asset detail view with the SHAP explanation data, and an alerts/flagged-activity view. Use font-mono for all numeric data as specified in the design doc, and the flag/up/down color tokens correctly — flag color only for risk alerts, up/down only for price movement, never mixed.
```

---

## Step 8 — News/DD feed integration

```
Read docs/PROJECT_PLAN.md section 4.3. Build a news feed feature in apps/web: integrate the CryptoPanic API as primary source (sentiment-tagged, filterable per-currency) and CoinDesk as secondary. Proxy both through an apps/web API route so the API keys stay server-side, not exposed to the client. Surface it as a feed view in the app, and where possible, cross-reference news timing against risk-score movement data from the core detection engine for the "risk score spiked after this news" angle mentioned in the plan. I'll need to provide the actual API keys — check for missing env vars and tell me exactly what to add to .env.local.
```

---

## Step 9 — Trading bot, Phase 1 (backtesting only)

```
Read docs/PROJECT_PLAN.md section 4.2. Build apps/bot as a strategy backtesting engine only — Phase 1 from the roadmap, no live trading, no real funds involved. It should: ingest historical Stellar DEX data (reuse data/pipelines ingestion where possible), let a strategy be defined in a simple config/DSL, run it against historical data, and report performance metrics (returns, drawdown, win rate). 

Critically: design the execution interface as a pluggable mode (simulate / alert / execute) even though only "simulate" is implemented now — per the plan, Phase 2 (alerts) and Phase 3 (non-custodial execution via Soroban session permissions) get built later against the same engine, so don't hardcode anything that assumes backtesting is the only mode this will ever run in.
```

---

## Step 10 — Later, once the grant funding cycle wraps

Not a prompt to run yet — a reminder for when you're ready:

```
Check the terms of any Drip/GiveTH/Grantfox funding received, confirm nothing's tied to LedgerLens staying public, then archive or set the Ledger-Lenz GitHub org repos to private. No migration needed at that point — Stellar Lense already has everything of value via the git-history-preserving migration in Step 2.
```

---

## How to work through this
Run one step, review what Claude Code actually did before moving to the next — don't queue up all 10 prompts back to back blind, especially Steps 2 and 4 where a bad migration or an incomplete rebrand pass compounds into every step after it. Steps 6 onward is where your design taste matters most — expect to iterate on the landing page prompt a few times rather than accepting the first pass.
