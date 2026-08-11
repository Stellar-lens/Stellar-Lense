# Contributing to Ledgerlens-dashboard

This repo is a small static site (HTML/CSS/vanilla JS ES modules, no build step, no
framework). Contributions that keep it that way are strongly preferred over ones that
introduce a bundler, framework, or runtime dependency — see [ARCHITECTURE.md](ARCHITECTURE.md)
for why.

## Setup

```bash
git clone https://github.com/Ledger-Lenz/Ledgerlens-dashboard.git
cd Ledgerlens-dashboard
npm install
```

## Running it locally

```bash
cp dashboard/config.js.example dashboard/config.js   # point at your API
npm run serve                                        # http://localhost:8080
```

You'll need a running [Ledgerlens-api](https://github.com/Ledger-Lenz/Ledegerlens-api)
instance to see real data — this repo has no backend of its own.

## Before opening a PR

```bash
npm run lint       # ESLint over dashboard/js and tests
npm run lint:css   # Stylelint over dashboard/styles.css
npm run format     # Prettier — run this, don't just check it
npm test           # node --test over tests/
```

All four run in CI on every PR; a failing one blocks merge.

## Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your change, run the checks above
4. If you touched `dashboard/js/api.js` or `dashboard/js/formatters.js`, add or update a
   unit test in `tests/` — both are pure/injectable specifically so they're testable
   without a browser
5. Manually verify in a browser against a running API (see above) — the unit tests cover
   the pure logic, not the DOM wiring
6. Submit a pull request with a clear description of what changed and why

Please open an issue before starting significant work so we can align on approach.

## Reporting issues

Use the bug report or feature request template under Issues. If you're reporting a
security issue, see [SECURITY.md](SECURITY.md) instead of opening a public issue.
