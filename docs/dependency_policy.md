# Dependency License Policy

LedgerLens ships only packages with OSI-approved permissive licenses.

## Allowed license families

- MIT
- Apache-2.0
- BSD (2-Clause, 3-Clause, BSD-Like)
- ISC
- MPL-2.0 (weak copyleft, file-level only — acceptable when no modifications
  are made to the MPL-licensed files)
- PSF / Python Software Foundation License
- CDDL (Common Development and Distribution License — review per package)
- Unlicense / Public Domain

## Blocked license families

The CI `license-vuln-scan` workflow blocks merges for packages carrying any
of the following:

| License | Reason |
|---------|--------|
| GPL-2.0 / GPL-3.0 | Strong copyleft — would require all shipped code to be GPL |
| AGPL-3.0 | Network copyleft — would require SaaS to publish source |
| LGPL-2.0 / LGPL-3.0 | Weak copyleft — acceptable **only** for dynamic linking; evaluate case-by-case |
| CC-BY-SA | Creative Commons share-alike — not designed for software |
| EUPL | European Union Public Licence — copyleft |

## Granting an exception

To use a package with a blocked license:

1. Open a PR with the dependency change.
2. Add an entry to the **Exceptions** table below, justifying why the license
   is acceptable for this use (e.g. "used only as an optional dev tool, never
   shipped in the container image").
3. Add the package name to the `--ignore-packages` list in the
   `.github/workflows/license-vuln-scan.yml` `python-licenses` job **and**
   in the `make license` target in `Makefile`.
4. Get sign-off from at least one maintainer.

## Exceptions

| Package | License | Rationale | Added by | Date |
|---------|---------|-----------|----------|------|
| *(none)* | | | | |

## Vulnerability response SLA

| Severity | Response target |
|----------|----------------|
| Critical | 48 hours — patch or pin to safe version |
| High | 7 days — patch, pin, or document accepted risk |
| Medium | 30 days — tracked in GitHub Issues |
| Low | Best-effort — tracked in GitHub Issues |
