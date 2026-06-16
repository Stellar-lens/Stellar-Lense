# Cross-Asset Coordinated Wash Trade Detection for Multi-Pair Manipulation

**Label:** `advanced` | `detection` | `research` | `feature-engineering`
**Difficulty:** Advanced
**Area:** `detection/feature_engineering.py`, `detection/benford_engine.py`, `run_pipeline.py`, `ingestion/`

> **Depends on:** Issue #004 (Per-Pair Feature Attribution) must be merged first. Cross-asset features are computed by comparing per-pair trade DataFrames. Without the per-pair pipeline split from #004, there is no clean way to obtain pair-separated trade frames for each wallet. Do not start this issue until #004 is merged.

---

## Summary

Current detection operates **per asset pair in isolation**: a wallet's wash-trading risk on `USDC/XLM` is computed independently from its activity on `BTC/XLM` or `AQUA/XLM`. This is a significant blind spot.

Sophisticated wash traders on the Stellar DEX execute **coordinated cross-asset cycles**: the same wallet cluster cycles assets through multiple pairs simultaneously. For example:
- Wallet A sells USDC for XLM on the USDC/XLM pair.
- Wallet B simultaneously sells XLM for BTC on the XLM/BTC pair.
- Wallet C completes the cycle: sells BTC for USDC on the BTC/USDC pair.

Each pair individually shows modest, plausibly legitimate activity. The coordinated cycle is only visible when all three pairs are analysed together.

This issue asks you to implement **cross-asset coordination detection** as a new feature group, and to extend the pipeline to compute these features using multi-pair trade data.

---

## Detailed Description

### New feature group: Cross-Asset Coordination Features

Implement `compute_cross_asset_features(wallet: str, all_pairs_df: pd.DataFrame) -> dict` in `detection/feature_engineering.py`:

This function receives a combined DataFrame of trades across **all** watched pairs for the wallet, along with a column `pair_id` identifying which pair each trade belongs to.

**Feature 1 — `cross_pair_trade_synchrony`** (float, 0–1):
The fraction of this wallet's trade timestamps where the wallet also trades on at least one other pair within a configurable synchrony window (default: 30 seconds). A high value means the wallet consistently trades across multiple pairs at the same moment — a strong coordination signal.

**Feature 2 — `net_asset_flow_deviation`** (float):
Compute the net asset flow for each asset the wallet touches across all pairs:
```
net_flow[asset] = Σ amount_received[asset] - Σ amount_sent[asset]
```
For a legitimate market maker, `net_flow` is non-zero (they accumulate or deplete inventories). For a wash trader completing a closed cycle, `net_flow[asset] → 0` for all assets over any time window. `net_asset_flow_deviation` is the **maximum absolute net flow across all assets, normalised by total volume** — a value close to 0 indicates a closed cycle (suspicious); a large value indicates genuine inventory management.

**Feature 3 — `cross_pair_counterparty_overlap`** (float, 0–1):
The Jaccard similarity of the wallet's counterparty sets across different pairs. Legitimate market makers have pair-specific counterparties (liquidity pools, specialists). Wash traders reuse the same sock-puppet wallets across pairs. This is: `|counterparties_pair_1 ∩ counterparties_pair_2| / |counterparties_pair_1 ∪ counterparties_pair_2|`.

**Feature 4 — `cross_pair_volume_correlation`** (float, -1 to 1):
Pearson correlation of trade volumes across pairs, bucketed by minute. Legitimate traders' pair-specific volumes are uncorrelated. Coordinated wash traders' volumes spike across pairs simultaneously, producing high positive correlation.

**Feature 5 — `pair_diversity_score`** (float, 0–1):
Shannon entropy of the wallet's volume distribution across pairs, normalised by `log(n_pairs)`. High entropy = volume spread evenly across many pairs (market maker). Low entropy = volume concentrated on one or two pairs (possibly legitimate, possibly wash).

### Integration with the pipeline

These features require **all pairs' trades for each wallet**, not just one pair's trades. After Issue #004 (per-pair feature matrix) is merged, the cross-asset features must be computed from the full multi-pair DataFrame and merged into each per-pair feature vector (as global wallet features that are pair-agnostic).

Extend `build_feature_matrix` to accept `all_pairs_df: pd.DataFrame | None` and call `compute_cross_asset_features` when provided.

### New Benford metric: Cross-pair MAD consistency

Extend `detection/benford_engine.py` with:
```python
def cross_pair_benford_consistency(per_pair_metrics: dict[str, dict]) -> float:
```
Where `per_pair_metrics` maps `pair_id -> benford_metrics_dict`. Returns the standard deviation of MAD scores across pairs. A low value means all pairs have similar Benford conformity — consistent wash trading. A high value means some pairs conform and others don't — potentially the pairs where wash trading is concentrated.

Add `cross_pair_mad_std` as a new feature column.

---

## Requirements

### Functional
- All five cross-asset features + `cross_pair_mad_std` must be computable without live Horizon data (using only the trade DataFrame already loaded by the pipeline).
- When fewer than 2 pairs are active for a wallet, cross-pair features must return sensible defaults (0.0 for synchrony/overlap/correlation, 1.0 for `net_asset_flow_deviation`, 0.0 for `pair_diversity_score`).
- Feature computation must handle missing timestamps (NaT) gracefully.
- `cross_pair_trade_synchrony` window size must be configurable via `Config.CROSS_PAIR_SYNCHRONY_WINDOW_SECONDS` (default: 30).

### Performance
- Cross-asset feature computation for 500 wallets across 5 pairs must complete in < 60 seconds on a single core.
- `cross_pair_volume_correlation` must use efficient pandas groupby/resample — not a nested loop.

### Security
- No new credentials or external API calls required.

### Testing strategy note
These features require multi-pair test fixtures — see the test section below for required fixture design.

### Documentation
- Add the 6 new features to the feature table in `README.md` under a new "Cross-Asset Coordination Features" group.
- Update `scripts/generate_synthetic_dataset.py` to generate realistic cross-asset feature values for both legitimate and wash-trading wallets.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_cross_asset_features.py`:

1. **`test_cross_pair_synchrony_high_for_coordinated_trades`** — construct a DataFrame where wallet A trades on pair 1 and pair 2 within 10 seconds for 80% of timestamps; assert `cross_pair_trade_synchrony ≈ 0.8`.
2. **`test_net_flow_near_zero_for_closed_cycle`** — wallet buys 100 USDC for XLM on pair 1 and sells 100 USDC for XLM on pair 2 within the same window; assert `net_asset_flow_deviation < 0.01`.
3. **`test_net_flow_nonzero_for_legitimate_inventory`** — wallet consistently buys USDC (net accumulation); assert `net_asset_flow_deviation > 0.5`.
4. **`test_counterparty_overlap_high_for_shared_counterparties`** — wallet trades with the same 3 wallets across both pairs; assert `cross_pair_counterparty_overlap ≈ 1.0`.
5. **`test_counterparty_overlap_zero_for_disjoint`** — wallet trades with completely different counterparty sets on each pair; assert `cross_pair_counterparty_overlap == 0.0`.
6. **`test_volume_correlation_high_for_synchronised_spikes`** — simulate simultaneous volume spikes on both pairs in the same minute buckets; assert `cross_pair_volume_correlation > 0.8`.
7. **`test_defaults_with_single_pair`** — wallet only trades on one pair; assert all cross-pair features return their documented default values.
8. **`test_cross_pair_mad_std_zero_for_identical_distributions`** — same Benford metrics on both pairs; assert `cross_pair_mad_std ≈ 0.0`.
9. **`test_feature_matrix_includes_cross_asset_columns`** — run `build_feature_matrix` with `all_pairs_df` provided; assert all 6 new feature columns appear in the output.
10. **`test_synthetic_dataset_includes_cross_asset_columns`** — regenerate synthetic dataset; assert new feature columns are present and have non-trivially different distributions between label 0 and label 1.

Run with: `pytest tests/test_cross_asset_features.py -v`

All ten tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Financial data analysis / feature engineering / time-series statistics. Deep familiarity with `pandas` time-series operations, cross-correlation, and entropy metrics is required. Understanding of DEX market microstructure (order books, asset pairs, market making) is strongly preferred. Prior work in multi-market surveillance or cross-asset fraud detection is a major plus.

When commenting to claim this issue, please include:
- Your background in financial data analysis or market surveillance.
- Experience with multi-asset or cross-market anomaly detection.
- A brief description of how you would implement `net_asset_flow_deviation` efficiently for wallets with thousands of trades across many pairs.
- Any academic or industry research you have done on coordinated manipulation detection.

This issue addresses a detection gap that sophisticated wash traders are actively exploiting across DEX platforms globally. It is a substantive research contribution to the state of DeFi market integrity tooling.
