# LedgerLens TLA+ Specification

This directory contains a formal specification of the LedgerLens smart contract's state machine written in TLA+. The specification models score writes, the embargo gate, breach counter, risk band state, the delegation chain, and the WASM upgrade governance state machine.

## Invariants Modelled

The following critical invariants are encoded and verified:
1. **Historical Max Monotonicity**: `hwm` never decreases.
2. **Embargo Gate Soundness**: The embargo gate blocks score modifications / evaluations when an embargo is active.
3. **Breach Counter State Machine**: The breach counter correctly increments on thresholds and resets on clean submissions or manual resets.
4. **Delegation Acyclicity**: Enforces that no cyclical score delegation loops exist.
5. **Cooldown Enforcement**: Ensures a minimum time delay between valid score submissions.
6. **Score Floor Enforcement**: Prevents high-risk wallets (those that hit `HWM_THRESHOLD`) from having their scores forced below `FLOOR_VALUE`.

## WASM Upgrade State Machine

The upgrade flow (`propose_upgrade` → timelock → `execute_upgrade` or `veto_upgrade`) is the highest-stakes state machine in the contract. It is modelled with dedicated state variables and three actions:

### Modelled State Variables
- `upgrade_pending` — boolean flag indicating whether a proposal is active (`DataKey::PendingUpgrade`)
- `proposed_wasm_hash` — the WASM hash of the pending upgrade (`UpgradeProposal.new_wasm_hash`)
- `proposal_time` — ledger timestamp when the proposal was created (`UpgradeProposal.proposed_at`)
- `executable_time` — earliest timestamp at which the upgrade may be executed (`UpgradeProposal.executable_after`)
- `proposed_by` — the admin address that proposed the upgrade (`UpgradeProposal.proposed_by`)

### Modelled Actions
| TLA+ Action | Contract Equivalent | Guards Modelled |
|---|---|---|
| `ProposeUpgrade(caller, h)` | `propose_upgrade` | `caller = Admin`, `~upgrade_pending` (→ `Error::UpgradeAlreadyPending`) |
| `ExecuteUpgrade(caller)` | `execute_upgrade` | `caller = Admin`, `upgrade_pending` (→ `Error::NoPendingUpgrade`), `now >= executable_time` (→ `Error::UpgradeNotReady`) |
| `VetoUpgrade(caller)` | `veto_upgrade` | `caller = Admin`, `upgrade_pending` (→ `Error::NoPendingUpgrade`) |

### Modelled Identity
- `Admin` — a constant wallet that exclusively controls upgrade actions (modelled as `caller = Admin` guard)
- `Service` — a constant wallet that is verified *not* to be able to perform any upgrade action (its `caller` value fails the guard)

### Upgrade Invariants
1. **ProposedByAdminOnly**: `upgrade_pending ⇒ proposed_by = Admin`. A pending proposal was always created by the Admin; the `Service` identity (or any other wallet) cannot create one.
2. **ExecutableAfterProposalTime**: `upgrade_pending ⇒ executable_time ≥ proposal_time`. The timelock window is always non-negative.
3. **ProposalFieldsZeroedWhenIdle**: `¬upgrade_pending ⇒` all proposal fields are reset to sentinel values (zero/"None").
4. **Timelock Guarantee**: Execution never succeeds before the timelock elapses — this is enforced by the guard on `ExecuteUpgrade` (`now ≥ executable_time`) and verified by the model checker: no reachable behavior can execute an upgrade prematurely. A veto is always possible regardless of timing because `VetoUpgrade` has no time constraint; the action is enabled whenever `upgrade_pending = TRUE`.

### How to Install and Run TLC

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
   java -jar tla2tools.jar LedgerLens.tla
   ```

### Output

TLC performs an exhaustive breadth-first search of all reachable states (bounded by `StateConstraint`).
- If it prints **"No errors"**, all specified invariants hold in all reachable states up to depth 10.
- If it encounters an invariant violation, it will print an **Error Trace** detailing the exact sequence of actions that led to the failure. This trace can then be converted into a Rust unit test to confirm and patch the vulnerability in the smart contract.
