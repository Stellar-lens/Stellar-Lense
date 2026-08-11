# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Formal design token system in `styles.css` — spacing/type/radii/motion/z-index scales,
  applied everywhere a value already matched a scale step exactly.
- `dashboard/styleguide.html` — every component/variant rendered against the real
  stylesheet, with its own theme toggle, no API required. See
  [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).
- `tests/design-tokens.test.js` — guards against a CSS custom property referenced
  dynamically from JS (`var(--${scoreClass(score)})`) silently not existing.

### Fixed

- `.asset-card .asset-avg`'s color has been broken since it was written: `render.js`
  builds `var(--${scoreClass(score)})`, which needed `--low`/`--medium`/`--high` tokens
  that were never defined — only `--green`/`--yellow`/`--red` existed. The number silently
  fell back to the inherited text color instead of showing risk-level color. Found while
  building the style guide; fixed by aliasing the missing tokens to the existing palette.
- `.score-pill`'s low/medium/high backgrounds are now theme-aware tokens
  (`--low-bg`/`--medium-bg`/`--high-bg`) instead of hardcoded dark-theme hex values that
  never adapted when the light theme shipped.

## [1.0.0] — 2026-08-11

First release of the dashboard as what it was always meant to be: a standalone static
client, not a monorepo duplicating the other four `Ledger-Lenz` repos.

### Changed

- Removed the duplicated `api/`, `ingestion/`, `detection/`, `contracts/`, and their tests
  — that code belongs in Ledegerlens-api, Ledgerlens-data, Ledgerlens-core, and
  Ledgerlens-contract respectively.
- Rewrote `dashboard/app.js` (now `dashboard/js/app.js`, split into modules) to match
  Ledegerlens-api's actual response contract — it previously expected a wrapper shape
  and field names the deployed API has never returned.
- Rewrote the README's Repository Structure, Quick Start, API Reference, Configuration,
  and Testing sections for the dashboard-only scope; fixed dead links to a nonexistent
  `github.com/Ledger-Lenz/Ledgerlens-api` (real repo is `Ledegerlens-api`) and to a
  wrong GitHub org (`Inkman007` → `Ledger-Lenz`).

### Added

- `dashboard/js/{constants,formatters,api,render}.js` — the former single-file `app.js`
  split so the pure logic is unit-testable (`tests/formatters.test.js`,
  `tests/api.test.js`, run via `node --test`).
- `tests/dashboard.integration.test.js` — mounts the real `dashboard/index.html` in
  `jsdom` with a mocked `fetch` and exercises the DOM wiring end to end (filtering,
  sorting, theme toggle, copy-to-clipboard, the full score-lookup path including a
  simulated 404) — `render.js` and `app.js` were previously untested.
- ESLint, Stylelint, and Prettier configs, wired into a GitHub Actions CI workflow.
- Client-side wallet/asset-pair format validation before hitting the API.
- Retry-with-backoff for the score lookup on transient (5xx/network) failures.
- Abort-in-flight-requests on each refresh cycle, so overlapping auto-refresh and manual
  refresh can't race and show stale data.
- Manual refresh button and a last-updated timestamp.
- Loading skeleton for the stats row.
- Filtering and sorting for the alerts table; filtering for the asset ranking grid.
- Copy-to-clipboard for wallet addresses in the alerts table.
- Wallet/pair lookup persisted to `localStorage` across visits.
- Light theme + toggle (persisted), alongside the original dark theme.
- Favicon, Open Graph/meta description tags.
- Skip-to-content link, `aria-label`s, live regions, keyboard-operable sortable headers,
  and visible focus outlines.
- `LICENSE` (MIT) — referenced by the README's badge but never actually present before.
- `CONTRIBUTING.md`, `SECURITY.md`, `ARCHITECTURE.md`, issue/PR templates, `CODEOWNERS`.

### Fixed

- `.env.example`, `pytest.ini`, `requirements.txt`, and friends removed — none of them
  applied to a static site with no server-side code.
- README's `GET /score` example used a wallet address containing `0`, which isn't valid
  Stellar base32 (the alphabet excludes `0`/`1`/`8`/`9`) — caught while writing the
  integration tests, which need an actually-valid example wallet to test against.

[1.0.0]: https://github.com/Ledger-Lenz/Ledgerlens-dashboard/releases/tag/v1.0.0
