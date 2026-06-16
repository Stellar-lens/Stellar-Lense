# Adversarial Robustness Evaluation and Hardening of the Ensemble ML Models

**Label:** `advanced` | `security` | `detection` | `research`
**Difficulty:** Advanced
**Area:** `detection/`, new `scripts/adversarial_eval.py`

> **Dual-skill requirement:** This issue sits at the intersection of adversarial ML research and production Python engineering. A contributor with only an engineering background will likely implement the attacks mechanically without meaningful threat modelling; a contributor with only a research background may write prototype-quality code that cannot be merged into production. **We are specifically looking for someone who has done both**: implemented adversarial examples (in any domain) AND written production-grade Python code with tests. Demonstrate both capabilities clearly when applying.
>
> **Note on data:** The benchmark in `reports/adversarial_benchmark.json` can be generated against the synthetic dataset, but the evasion rates will be optimistic (the synthetic data is too clean). If Issue #009 (labelled dataset) has been completed, use the real dataset instead — the benchmark will be significantly more meaningful.

---

## Summary

The ensemble ML classifiers (Random Forest, XGBoost, LightGBM) are currently evaluated only on held-out samples from the **same distribution** as training data. This evaluates accuracy but not **robustness**: a sophisticated wash trader who understands the feature space can systematically manipulate their trading behaviour to evade detection while still carrying out wash trading.

This issue asks you to:
1. Formalise the **adversarial threat model** for wash-trading detection evasion.
2. Implement **feature-space adversarial attacks** that generate minimally modified feature vectors that cross the decision boundary from `label=1` (wash trading) to `label=0` (clean).
3. Quantify the **evasion rate** and **minimum modification cost** for each model in the ensemble.
4. Propose and implement at least **two concrete hardening measures** that measurably reduce the evasion rate.
5. Document findings and mitigations in `docs/adversarial_robustness.md`.

---

## Detailed Description

### Threat model

A sophisticated adversary can:
- Observe the open-source feature definitions in `detection/feature_engineering.py`.
- Adjust trading behaviour (e.g. vary trade sizes, introduce noise, space out round-trips, use more counterparties) to shift feature values away from the wash-trading distribution.
- They cannot directly access the trained model weights, but can black-box probe the deployed API's score endpoint.

**In-scope attacks:**
1. **Feature-space gradient attack (white-box)**: Modify a wash-trading feature row with the minimum L1-norm perturbation required to flip the ensemble prediction from `label=1` to `label=0`. Implementable as a projected gradient descent on the feature vector against the ensemble's soft probability output.
2. **Benford evasion attack**: Generate wash trading amounts from a log-uniform distribution that conforms to Benford's Law (this is achievable by scaling fixed trade amounts by random log-uniform noise). Measure how many Benford-conforming wash traders the ML layer still catches.
3. **Counterparty diversification attack**: Increase `counterparty_concentration_ratio` by routing wash trades through multiple wallets. Measure the score reduction per additional counterparty wallet.

**Out-of-scope (for this issue):**
- On-chain cost of evasion (gas fees, slippage) — this is an economic analysis, not an ML evaluation.
- Adaptive attacks that retrain on score feedback (black-box query attacks).

### Part 1: Adversarial attack implementations (`scripts/adversarial_eval.py`)

Implement three attack functions:

```python
def gradient_feature_attack(
    feature_row: pd.Series,
    models: dict,
    max_iterations: int = 100,
    step_size: float = 0.01,
    target_prob: float = 0.45,  # just below ML_FLAG_THRESHOLD
) -> tuple[pd.Series, float]:
    """Perturb feature_row until ensemble P(wash) < target_prob.
    Returns (perturbed_row, l1_distance_from_original)."""

def benford_conforming_amounts(
    n_trades: int,
    base_amount: float,
    seed: int = 42,
) -> pd.Series:
    """Generate wash-trade amounts that conform to Benford's Law."""

def diversified_counterparty_simulation(
    n_counterparties: int,
    trades_per_counterparty: int,
    wallet: str,
) -> pd.DataFrame:
    """Simulate wash trades spread across n_counterparties."""
```

### Part 2: Evasion rate benchmark

For each attack, compute:
- **Evasion rate**: fraction of positives (`label=1`) in the test set that achieve `score < RISK_SCORE_FLAG_THRESHOLD` after the attack.
- **Minimum L1 cost** (for gradient attack): median L1 perturbation required to evade detection.
- **Benford evasion score distribution**: scores of Benford-conforming wash traders vs. non-conforming.

Report these as a JSON benchmark in `reports/adversarial_benchmark.json`.

### Part 3: Hardening measures

Implement and evaluate **at least two** of the following:

**Option A — Randomised feature noise during training (label smoothing + noise injection)**:
Add Gaussian noise to training features at training time so the model learns robust decision boundaries rather than memorising clean examples. Controlled by `TRAINING_NOISE_SIGMA` config parameter.

**Option B — Behavioral consistency check (temporal feature disagreement detection)**:
If a wallet's short-window Benford MAD is anomalously low relative to its long-window MAD (i.e. recent trades look clean but historical trades don't), add a `benford_temporal_divergence` feature that captures this discrepancy. A sophisticated evader who cleans up recent behaviour leaves a temporal signature.

**Option C — Ensemble disagreement flag**:
The current `confidence` score already captures inter-model disagreement. Hardening: if any two models in the ensemble disagree by > 0.3 in probability, treat the wallet as requiring review regardless of the average score. Add `high_disagreement_flag: bool` to the `RiskScore` output.

For each implemented hardening measure, report the before/after evasion rate on the adversarial benchmark.

### Part 4: Documentation (`docs/adversarial_robustness.md`)

A structured technical document covering:
- Threat model and attacker capabilities.
- Attack methodology and implementation details.
- Benchmark results (tables with evasion rates before/after hardening).
- Limitations and future work.

---

## Requirements

### Correctness
- Gradient attack must use the **ensemble's combined probability** (not individual model outputs) as the attack objective.
- The attack must respect feature value ranges (e.g. probabilities must stay in [0, 1], counts must stay ≥ 0) — use projected gradient descent with box constraints.

### Reproducibility
- All attack benchmarks must use a fixed random seed and produce identical results on re-run.
- `reports/adversarial_benchmark.json` must be committed alongside the PR.

### Security
- Adversarial attack code must be in `scripts/` only — not wired into the production inference path. The hardening measures go into `detection/`.
- `docs/adversarial_robustness.md` must **not** provide a step-by-step recipe for conducting real wash trading — describe attack methodology at the statistical level, not as operational trading instructions.

### Documentation
- `docs/adversarial_robustness.md` must be complete and self-contained.
- Reference at least two academic papers on adversarial ML in financial fraud detection.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_adversarial.py`:

1. **`test_gradient_attack_reduces_score`** — run the gradient attack on a synthetic `label=1` feature row with a trained model; assert the resulting score is < the original score.
2. **`test_gradient_attack_respects_feature_bounds`** — after the gradient attack, assert all feature values remain in valid ranges (no negatives for ratio features, no values > 1 for proportion features).
3. **`test_benford_conforming_amounts_pass_mad_test`** — generate 1000 wash-trade amounts using `benford_conforming_amounts`; assert the MAD of their leading-digit distribution is < `MAD_NONCONFORMITY_THRESHOLD` (0.015).
4. **`test_diversified_counterparty_reduces_concentration`** — simulate with 1 vs. 10 counterparties; assert `counterparty_concentration_ratio` decreases monotonically.
5. **`test_hardening_reduces_evasion_rate`** — with at least one hardening measure implemented, assert evasion rate on the gradient attack benchmark is measurably lower (> 5 percentage points) than the unhardened baseline.
6. **`test_adversarial_benchmark_json_schema`** — assert `reports/adversarial_benchmark.json` exists and contains `evasion_rate`, `median_l1_cost`, and `hardening_results` keys.

Run with: `pytest tests/test_adversarial.py -v`

All six tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Adversarial ML / security research / applied ML. Deep familiarity with adversarial examples, projected gradient descent, and ML robustness evaluation is required. Experience with financial fraud detection or adversarial robustness in tabular ML is a strong plus. Academic research background is welcome.

When commenting to claim this issue, please include:
- Your background in adversarial ML or security research.
- Papers or projects you have contributed to in adversarial robustness, fraud detection, or financial ML.
- Your preferred implementation approach for the gradient attack (gradient estimation for black-box models vs. direct gradient access for white-box).
- Which hardening measures you intend to implement and a brief rationale for each choice.

This issue is at the frontier of applied ML security. The results will directly inform how detection-resistant LedgerLens is and what wash traders would need to do to evade it — knowledge that makes the system substantially more robust.
