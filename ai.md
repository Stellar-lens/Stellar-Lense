# LedgerLens Ecosystem

LedgerLens is split across six repositories under the
[Ledger-Lenz](https://github.com/Ledger-Lenz) GitHub organisation. This
document maps how they fit together.

| Repository | Role |
|---|---|
| [Ledegerlens-api](https://github.com/Ledger-Lenz/Ledegerlens-api) | **This repository.** FastAPI REST API, ingestion pipeline, Benford's Law + ML detection engine, and the Soroban risk-score contract interface. |
| [Ledgerlens-core](https://github.com/Ledger-Lenz/Ledgerlens-core) | Shared core library — common types, configuration, and orchestration logic used across the LedgerLens services. |
| [Ledgerlens-contract](https://github.com/Ledger-Lenz/Ledgerlens-contract) | Standalone Soroban smart contract project for the on-chain LedgerLens risk-score registry (`submit_score` / `get_score`), deployed independently of the API. |
| [Ledgerlens-data](https://github.com/Ledger-Lenz/Ledgerlens-data) | Datasets and data tooling — labelled wash-trade patterns, historical SDEX trade dumps, and dataset generation scripts used to train the ML ensemble. |
| [Ledgerlens-dashboard](https://github.com/Ledger-Lenz/Ledgerlens-dashboard) | Web dashboard for browsing LedgerLens Risk Scores, alerts, and asset risk rankings, consuming this API. |
| [.github](https://github.com/Ledger-Lenz/.github) | Organisation-wide defaults — community health files, issue/PR templates, and shared CI workflows for all LedgerLens repositories. |

## How they connect

```
Ledgerlens-data  ──► Ledegerlens-api (ingestion + detection + scoring)
                          │
                          ├──► Ledgerlens-contract (on-chain score registry)
                          └──► Ledgerlens-dashboard (consumes REST API)

Ledgerlens-core   ──► shared by all of the above
.github           ──► org-wide CI/community config for all of the above
```
