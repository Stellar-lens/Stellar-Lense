# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this
project adheres to [Semantic Versioning](https://semver.org/).

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

[1.0.0]: https://github.com/Ledger-Lenz/Ledgerlens-dashboard/releases/tag/v1.0.0
