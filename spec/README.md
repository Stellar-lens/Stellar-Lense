# LedgerLens TLA+ Specification

This directory contains a formal specification of the LedgerLens smart contract's state machine written in TLA+. The specification models score writes, the embargo gate, breach counter, risk band state, the delegation chain, and the **adaptive rate-limit token bucket** (issue #405).

## Invariants Modelled

The following critical invariants are encoded and verified:

### Existing Invariants
1. **Historical Max Monotonicity**: `hwm` never decreases.
2. **Embargo Gate Soundness**: The embargo gate blocks score modifications / evaluations when an embargo is active.
3. **Breach Counter State Machine**: The breach counter correctly increments on thresholds and resets on clean submissions or manual resets.
4. **Delegation Acyclicity**: Enforces that no cyclical score delegation loops exist.
5. **Cooldown Enforcement**: Ensures a minimum time delay between valid score submissions.
6. **Score Floor Enforcement**: Prevents high-risk wallets (those that hit `HWM_THRESHOLD`) from having their scores forced below `FLOOR_VALUE`.

### Token-Bucket Invariants (new — issue #405)

7. **TokensNeverExceedCapacity** (`INV-TB-1`): The effective token count seen by the next `SubmitScore` call (computed by `RefillCount`) never exceeds the current global capacity `tb_capacity`. This holds both under normal operation and immediately after a capacity *reduction* — the lazy-truncation contract (bucket state is clamped on the next read, not eagerly rewritten) means raw stored tokens may temporarily exceed the new cap, but `RefillCount` always clamps to `tb_capacity`, so no wallet can burst above the new limit.

8. **TokensNonNegative** (`INV-TB-2`): Stored token counts are always ≥ 0. Because `SubmitScore` only proceeds when `RefillCount > 0`, and then stores `refilled - 1 ≥ 0`, this is structurally guaranteed — the invariant makes it machine-checkable.

9. **CapacityReductionCapsNextBurst** (`INV-TB-3`): Mirrors `INV-TB-1` and is stated separately for clarity: after `SetBurstCapacity` reduces the capacity, the *effective* tokens available on the next refill are bounded by the new capacity. This directly catches the class of off-by-one bugs where a burst larger than the new capacity is allowed right after a capacity reduction.

10. **RefillAnchorNotInFuture** (`INV-TB-4`): `tb_last_refill[w] ≤ now` at all times. If this were violated, `elapsed` would underflow and the refill count would be computed incorrectly, potentially granting extra tokens.

11. **CapacityWithinBounds** (`INV-TB-5`): `tb_capacity` is always within `[MIN_CAPACITY, MAX_CAPACITY]`. This ensures `SetBurstCapacity` can never lock wallets permanently (capacity = 0) or open the bucket arbitrarily wide.

### Token-Bucket Temporal Properties (new — issue #405)

12. **TokenExhaustionBlocksSubmit** (`PROP-TB-1`): When a `SubmitScore` drains the bucket to 0, only that very submission is accepted at `now`; subsequent submissions for the same wallet are blocked until tokens refill (i.e. until at least one `COOLDOWN` tick has elapsed).

13. **BurstNeverExceedsNewCapacity** (`PROP-TB-2`): After a capacity *increase*, the effective available tokens on the next refill still never exceed the new (higher) capacity. This is the upward-direction companion to `INV-TB-3`.

## Variables

| Variable | Type | Description |
|---|---|---|
| `score` | `Wallet → ℕ` | Latest submitted risk score |
| `hwm` | `Wallet → ℕ` | Historical high-water mark (running maximum score) |
| `breach_count` | `Wallet → ℕ` | Consecutive breach counter |
| `last_submit_time` | `Wallet → ℕ` | Ledger timestamp of last accepted submission |
| `embargo_expiry` | `Wallet → ℤ` | Embargo expiry timestamp (0 = none, −1 = permanent) |
| `delegate` | `Wallet → Wallet ∪ {"None"}` | Delegation mapping |
| `now` | `ℕ` | Monotonically advancing ledger timestamp |
| `tb_tokens` | `Wallet → ℕ` | Current token count per wallet bucket |
| `tb_last_refill` | `Wallet → ℕ` | Last-refill anchor timestamp per wallet |
| `tb_capacity` | `ℕ` | Global burst capacity (max tokens per bucket) |

## Model-Check Results

The model was checked with TLC using the configuration in `LedgerLens.cfg`.

### Model parameters

| Constant | Value | Rationale |
|---|---|---|
| `Wallets` | `{"W1", "W2"}` | Two wallets give sufficient pair-interaction coverage |
| `Scores` | `{0, 50, 80}` | Covers below-floor, at-threshold, and above-threshold cases |
| `COOLDOWN` | `1` | Unit cooldown makes all time arithmetic directly visible |
| `HWM_THRESHOLD` | `80` | Matches default production value |
| `FLOOR_VALUE` | `20` | Matches default production value |
| `RISK_THRESHOLD` | `50` | Mid-range threshold |
| `MIN_CAPACITY` | `1` | Minimum legal capacity (legacy flat-cooldown behaviour) |
| `MAX_CAPACITY` | `3` | Upper exploration bound; 3 tokens exposes multi-burst paths |
| `StateConstraint` | `now ≤ 5` | Bounds state-space while covering ≥ 2 full refill cycles |

### Outcome

**No invariant violations found.** All 11 invariants and 4 temporal properties
(including the 5 new token-bucket invariants and 2 new temporal properties) held
across all reachable states within the `now ≤ 5` bound.

To reproduce:

```bash
# Download TLA+ Tools if not already present
curl -L -o tla2tools.jar \
  https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar

# Run TLC
java -jar tla2tools.jar -config LedgerLens.cfg -depth 8 LedgerLens.tla
```

Expected output: `Model checking completed. No error has been found.`

### Invariant violations and bug reports

Any invariant violation TLC produces should be converted into a Rust regression
test targeting `contracts/ledgerlens-score/src/` and filed as a bug against the
Rust implementation — **not** silently patched in the spec alone. The spec must
remain a faithful model of the implemented behaviour, not an idealised version of it.

During development of this extension (issue #405), no violations were found in the
token-bucket invariants. The `CapacityReductionCapsNextBurst` invariant (`INV-TB-3`)
and `BurstNeverExceedsNewCapacity` (`PROP-TB-2`) are the most valuable checks: they
exhaustively cover the set of refill/consume sequences that hand-written unit tests
are unlikely to enumerate, specifically the edge case where `SetBurstCapacity`
reduces capacity between two `SubmitScore` calls.

## How to Install and Run TLC

TLC is the official model checker for TLA+ specifications. You can run TLC from the command line using Java.

### Prerequisites

You must have Java installed (JRE 11+ recommended).

### Running TLC

1. Download the TLA+ Tools (`tla2tools.jar`) if it isn't already present:
   ```bash
   curl -L -o tla2tools.jar https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar
   ```

2. Run the TLC model checker on the specification using the configuration file:
   ```bash
   java -jar tla2tools.jar -config LedgerLens.cfg -depth 8 LedgerLens.tla
   ```

### Output

TLC will explore all possible states up to a depth of 8 state transitions.
- If it prints **"No errors"**, all specified invariants hold in all reachable states up to depth 8.
- If it encounters an invariant violation, it will print an **Error Trace** detailing the exact sequence of actions that led to the failure. This trace should be converted into a Rust unit test to confirm and patch the vulnerability in the smart contract.
