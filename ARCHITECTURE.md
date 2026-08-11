# Architecture

## Why no framework, no bundler

This dashboard is a handful of read-only views over a REST API: a stats row, a score
lookup form, an alerts table, and an asset ranking grid. That doesn't need React, a
bundler, or a package of runtime dependencies — vanilla JS ES modules loaded directly by
the browser (`<script type="module">`) cover it with zero build step and zero supply-chain
surface beyond the dev tooling. If the dashboard's scope grows well past this (routing,
complex client state, a component tree), that calculation should be revisited — but don't
add the framework preemptively.

## Module layout

```
dashboard/
├── index.html            Markup + inline critical styles for dynamic bits
├── styles.css             All styling, including the light/dark theme variables
├── config.js.example      Copy to config.js to set window.LEDGERLENS_API
├── favicon.svg
└── js/
    ├── constants.js        Shared config: thresholds, patterns, refresh interval
    ├── formatters.js        Pure functions: score → class/label/pill, timestamp, wallet shortening
    ├── api.js               Fetch wrapper: apiFetch (typed errors) + apiFetchWithRetry (backoff)
    ├── render.js             DOM-writing functions, given data + element refs
    └── app.js                Orchestrator: wires api.js + render.js to DOM events, owns state
```

The split follows one rule: **anything that doesn't need `window`/`document` is pure and
lives in `constants.js`/`formatters.js`/`api.js`**, so it can be unit tested with Node's
built-in test runner (`tests/`) without a browser or a DOM shim. `render.js` and `app.js`
are DOM-coupled and are verified manually (see [CONTRIBUTING.md](CONTRIBUTING.md)) — adding
a headless-browser dependency just to cover them hasn't been worth it at this size.

## Data flow

```
Ledegerlens-api  ──HTTP──▶  dashboard/js/api.js  ──▶  dashboard/js/app.js  ──▶  dashboard/js/render.js  ──▶  DOM
                                                              │
                                                    localStorage (theme, last lookup)
```

`app.js` polls `/health`, `/alerts/recent`, and `/assets/risk-ranking` every 60s (see
`REFRESH_INTERVAL_MS` in `constants.js`), aborting the previous cycle's in-flight requests
before starting a new one so a slow response can't land after a newer refresh already has.
`/score/{wallet}/{pair}` is fetched on demand from the lookup form, with retry-with-backoff
since it's a single user-initiated request worth being resilient about.

## Why the API contract looks the way it does

`dashboard/js/api.js` and the field names in `render.js` (`asset_pair`, `average_score`,
`flagged_wallets`, `reason` on alerts — not `asset_code`/`avg_score`/`flagged_wallet_count`/
`benford_flag`+`ml_flag`) match [Ledegerlens-api](https://github.com/Ledger-Lenz/Ledegerlens-api)'s
**actual** deployed contract, not the aspirational one described in earlier drafts of the
main README. If you're adding a feature that needs a field the API doesn't return, that's
an API repo change first — see the note in the README's API Reference section (§11).
