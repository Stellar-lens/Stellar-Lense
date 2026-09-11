---
title: "Add Python SDK Client Library for Stellar Lense API with Typed Pydantic Models"
labels: ["difficulty: intermediate", "area: sdk", "type: feature"]
assignees: []
---

## Summary
Exchange engineers integrating Stellar Lense into their risk systems must write their own HTTP client code against the REST API. A first-party Python SDK (`stellar_lense`) with typed request/response models, automatic retry, and async support reduces integration time from days to hours.

## Objectives
- [ ] Create `packages/stellar-lense-sdk/` as a standalone Python package
- [ ] Implement `StellarLenseClient(base_url, api_key)` with methods mirroring all public API endpoints
- [ ] All responses typed as Pydantic v2 models; raise `StellarLenseAPIError` on non-2xx responses
- [ ] Async client: `AsyncStellarLenseClient` using `httpx.AsyncClient`
- [ ] Publish to PyPI as `stellar-lense-sdk`; version synced with API version

## Definition of Done
- [ ] `from stellar_lense import StellarLenseClient; client.get_score("G...")` works against a live server
- [ ] Async client tested with `asyncio.gather` for concurrent scoring
- [ ] SDK docs auto-generated from docstrings via pdoc
- [ ] Integration test runs SDK against a local test server
