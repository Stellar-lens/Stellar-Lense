# Executable Architecture Guide (summary)

This document provides a compact, executable view of the LedgerLens Core architecture to help new contributors find code, tests, docs, and deployment boundaries.

Runtimes and primary directories
- HTTP API: api/ (FastAPI / Starlette handlers and middleware)
- Workers & background: workers/ or tasks invoked by services (search repository for worker entrypoints)
- Data stores: settings.db_path (SQLite by default), external DBs or services noted in config/settings

Data ownership and trust boundaries
- API requests: api/ handlers own request validation and authorization
- Detection results: detection/ (authoritative for model outputs)
- Secrets: configuration system (config/) — do not commit secrets

Contributor journeys (short)
- First fix: find a failing test or small bug in api/, make a minimal change, add a test alongside.
- Add a detector: update detection/ with model + tests, provide migration notes in docs/ and link to CI issue.
- Schema migration: create migration script, add compatibility tests, update docs/ and roadmap issue.

Document status
- This is an initial, living map (experimental). Expand into diagrams and CI checks as separate follow-ups.

References
- Roadmap and backlog: ISSUE #625
