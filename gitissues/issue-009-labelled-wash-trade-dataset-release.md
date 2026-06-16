# Build and Release a Labelled Stellar SDEX Wash-Trade Dataset

**Label:** `advanced` | `data` | `research` | `roadmap`
**Difficulty:** Advanced
**Area:** `scripts/`, `detection/`, data pipeline, research

> **Scope warning — research task:** This issue has a wider variance than any other issue in this repo. The engineering components (mining scripts, labelling pipeline) are well-scoped, but the data quality and human-review steps are inherently uncertain. Real Horizon data may be noisier than expected, Benford signals may not cleanly separate on certain asset pairs, and the manual review sample (50–100 wallets) requires careful judgement. Claimants must have prior experience with time-series data analysis on a public blockchain before applying. Maintainer will do a mid-point check-in to assess whether scope needs adjustment.
>
> **Helps:** Issues #010 (Continuous Retraining) and #013 (Adversarial Robustness) both benefit significantly from real labelled data — a synthetic dataset severely limits those evaluations. Completing this issue first substantially raises the value of both.

---

## Summary

The ensemble ML models are currently trained on `scripts/generate_synthetic_dataset.py` — a synthetic dataset with no real on-chain observations. The `README.md` roadmap explicitly lists "Open dataset release: labelled SDEX wash trade patterns" as a Phase 3 goal.

Training on synthetic data is a significant accuracy limitation: the synthetic generator produces clean, linearly separable distributions that do not capture the statistical complexity of real wash trading. A model trained on synthetic data will generalise poorly to novel wash-trading strategies and will produce unreliable confidence scores.

This issue asks you to design and implement a **data mining pipeline** that constructs a ground-truth labelled dataset from publicly available on-chain Stellar DEX history, then release it as a versioned Parquet file under `data/` with a full provenance document.

This is an audacious, research-grade task. It requires blockchain forensics, statistical methodology, and careful documentation. The resulting dataset becomes the foundation for all future model improvements.

---

## Detailed Description

### Labelling strategy

Ground-truth labels for wash trading cannot come from automated pattern-matching alone (that would be circular). The labelling strategy must combine **at least two independent signals**:

**Signal 1 — Round-trip detection (algorithmic):**
Identify wallet pairs `(A, B)` where:
- A sells asset X to B and B sells asset X back to A within a configurable time window (e.g. ≤ 100 ledger closes, ≈ 5–8 minutes).
- The amounts are within ±5% of each other (accounting for slippage and fees).
- The net asset transfer for both wallets approaches zero over the window.

Implement this in `scripts/mine_roundtrips.py` using the Horizon trades endpoint and a sliding window over trade timestamps.

**Signal 2 — Funding source clustering (structural):**
Apply the existing `detection/wallet_graph.py` funding-graph analysis to identify clusters of accounts funded by the same source within a short time window. Accounts in a tight cluster (Jaccard similarity > 0.7) that also appear in round-trip pairs are strong candidates.

**Signal 3 — Manual review sample (human-verified):**
For accounts flagged by both signals 1 and 2, manually inspect 50–100 accounts using Stellar Expert or StellarBeat to verify that the flagging is plausible. Document the review in `data/labelling_notes.md`. Accounts reviewed and confirmed are labelled `1`; accounts reviewed and dismissed are labelled `0` and added to a blocklist that prevents re-labelling.

**Conservative labelling rule:**
- `label = 1` (wash trading): flagged by **both** signals 1 and 2.
- `label = 0` (legitimate): **no** flags from either signal, AND the wallet has > 50 trades with > 5 distinct counterparties.
- Accounts in the grey zone (flagged by only one signal, or too few trades to classify) are excluded from the dataset with `label = NaN`.

### Dataset schema

The output Parquet file must have exactly the columns produced by `detection/feature_engineering.py::build_feature_matrix`, plus:
- `label` (int: 0 or 1)
- `labelling_signal` (str: `"roundtrip_and_graph"` | `"roundtrip_only"` | `"graph_only"` | `"manual"`)
- `review_notes` (str: brief rationale for the label, or empty string)
- `data_window_start` (ISO datetime)
- `data_window_end` (ISO datetime)
- `n_trades` (int: number of trades used to build the feature row)

### Files to create

| File | Purpose |
|---|---|
| `scripts/mine_roundtrips.py` | CLI to detect round-trip trades from Horizon history |
| `scripts/build_labelled_dataset.py` | Orchestrates all three signals into a labelled Parquet |
| `data/labelling_notes.md` | Human review notes and methodology documentation |
| `data/dataset_card.md` | Dataset card: schema, statistics, known biases, licence |
| `scripts/README.md` | Update with new script docs |

---

## Requirements

### Data quality
- The released dataset must contain **≥ 500 labelled wallets** (≥ 200 positive, ≥ 300 negative).
- Class balance ratio must be documented in `data/dataset_card.md`.
- The dataset must cover **at least 3 distinct asset pairs** (e.g. USDC/XLM, BTC/XLM, AQUA/XLM).
- All features must be computable from the final dataset using only `detection/feature_engineering.py` — no external columns.

### Reproducibility
- `scripts/build_labelled_dataset.py` must be fully reproducible: given the same Horizon data window and parameters, it must produce the same output.
- A `data/build_config.json` file must document the exact parameters used to build the released dataset (date range, asset pairs, thresholds).

### Provenance and ethics
- The dataset must only contain publicly available on-chain data (Horizon API, no private sources).
- Wallet addresses in the dataset are public keys on a permissionless blockchain. Document this explicitly in `data/dataset_card.md`.
- The dataset must be released under the project's MIT licence.

### Security
- No API keys or credentials required for Horizon data mining.

### Documentation
- Update `README.md` to announce the dataset release and link to `data/dataset_card.md`.
- Update the roadmap to mark Phase 3 "Open dataset release" as complete.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_dataset_mining.py`:

1. **`test_mine_roundtrips_detects_known_pattern`** — construct a synthetic trade DataFrame with a deliberate round-trip (A→B then B→A within 5 minutes, amounts within 5%); assert the round-trip pair is detected by `mine_roundtrips.detect_roundtrip_pairs`.
2. **`test_mine_roundtrips_ignores_slow_return`** — same pattern but with a 2-hour gap; assert no round-trip is detected when `max_ledger_window` is set to 100 closes.
3. **`test_labelling_rule_requires_both_signals`** — provide a wallet flagged only by signal 1; assert `label = NaN` (excluded).
4. **`test_labelling_rule_positive`** — provide a wallet flagged by both signals 1 and 2; assert `label = 1`.
5. **`test_dataset_schema_matches_feature_matrix`** — load `data/synthetic_dataset.parquet` as a reference schema; assert the columns (excluding `label`, `labelling_signal`, `review_notes`, `data_window_*`, `n_trades`) match exactly those produced by `build_feature_matrix`.
6. **`test_build_config_json_exists_and_is_valid`** — assert `data/build_config.json` is valid JSON and contains `date_range_start`, `date_range_end`, `asset_pairs`, and `thresholds` keys.

Run with: `pytest tests/test_dataset_mining.py -v`

All six tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Blockchain data analysis / financial forensics / data engineering. Strong familiarity with Stellar Horizon API, `pandas` time-series operations, and statistical methodology required. Experience with graph analysis (`networkx`) is a strong plus.

This is a **research and engineering hybrid** — it is not a pure coding task. Applicants must be comfortable making methodological decisions about labelling heuristics and documenting those decisions rigorously.

When commenting to claim this issue, please include:
- Your experience with blockchain data analysis or financial fraud detection.
- Whether you have experience mining data from the Stellar Horizon API at scale.
- A brief (3–5 sentence) outline of your proposed approach to the round-trip detection logic.
- Any publications, datasets, or research projects you have contributed to in the fraud-detection or DeFi space.

This issue delivers the dataset that unlocks all future model quality improvements. It is the single highest-leverage contribution a researcher can make to this project.
