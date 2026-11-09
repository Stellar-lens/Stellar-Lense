# contracts/soroban/experimental

**Not deployed. Not built or tested by CI.** A separate Cargo workspace
(excluded from the one in `contracts/soroban/Cargo.toml`), kept for
reference.

This is the original `stellar-lense-score` contract and everything built
around it: a 13.5k-line `lib.rs` with 317 public functions (Verkle
commitments, ZK range proofs, multi-sig governance, escrow, dispute
committees, delegation, attestations, ...), its aggregator, test-support
crate, mock lending/AMM fixtures, replay/recovery/schema/fuzzing tools,
1,365 test snapshots, docs and deploy scripts.

The deployed contract is the much smaller
[`stellar-lense-registry`](../contracts/stellar-lense-registry): the
handful of functions the off-chain pipeline and a consuming protocol
actually use. Anything here that proves necessary should be ported into
the registry deliberately, with its own tests and review, not
re-enabled wholesale.

To build or test it anyway:

```bash
cd contracts/soroban/experimental
cargo test --workspace
```
