# Security Policy

## Scope

This repo is a static, read-only dashboard client with no backend, no authentication, and
no user data storage beyond a wallet/pair pair and a theme preference in `localStorage`.
Its attack surface is small, but not zero:

- XSS via unsanitized API response data rendered as `innerHTML` (see `dashboard/js/render.js`)
- Dependency vulnerabilities in the dev tooling (`package.json` devDependencies)
- Supply-chain risk in the CDN-hosted Google Fonts stylesheet loaded by `index.html`

Vulnerabilities in the API, detection engine, ingestion pipeline, or Soroban contract
belong to their own repos — see the main [README](README.md#16-related-repositories) for
links — and should be reported there instead.

## Reporting a Vulnerability

Please do **not** open a public issue for a security report. Instead, email
[victoruzoma874@gmail.com](mailto:victoruzoma874@gmail.com) with:

- A description of the issue and its potential impact
- Steps to reproduce
- Any relevant logs, payloads, or screenshots

We'll acknowledge within a few days and follow up once we've assessed it.
