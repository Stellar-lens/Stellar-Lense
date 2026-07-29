# Model feature compatibility

Every trained model now records a versioned feature contract in
`model_metadata.json`. The contract covers the ordered feature names and their
pandas dtypes. It complements the legacy, order-insensitive
`feature_schema_hash`, which remains in place for inference compatibility.

## Why order and type are part of the contract

Some estimators align inputs by column name, while other serialized estimators
consume positional arrays. A set-only comparison can therefore miss a reorder
that assigns values to the wrong learned feature. A dtype change can likewise
alter coercion, missing-value, or categorical behavior even when the name is
unchanged.

The `feature_contract_hash` is a SHA-256 digest of a canonical JSON payload
containing:

- `feature_contract_version`
- each feature name in training order
- the recorded dtype for each feature

The validator checks both the legacy schema hash and the complete contract hash
when they are present. A mismatch is reported as invalid metadata rather than a
normal compatibility difference.

## Compatibility policy

Strict validation is the default deployment policy:

| Change | Strict result | `--allow-additive` result |
|---|---|---|
| Identical names, order, and dtypes | compatible | compatible |
| Candidate adds features | incompatible | compatible |
| Candidate removes features | incompatible | incompatible |
| Shared features are reordered | incompatible | incompatible |
| Shared feature dtype changes | incompatible | incompatible |
| Legacy metadata has no dtypes | names-only validation | names-only validation |

Additive compatibility must be opted into because the candidate requires a
feature producer that older deployments may not provide. The report always
lists the added features so the rollout can coordinate producer and model
versions explicitly.

## Developer and CI command

Pass either model directories or direct `model_metadata.json` paths:

```bash
python -m scripts.validate_model_compatibility \
  --reference models/archive/20260701_120000 \
  --candidate models
```

Repeat `--candidate` to build a compatibility check against several archived
versions. Use `--json` for machine-readable CI output:

```bash
python -m scripts.validate_model_compatibility \
  --reference models \
  --candidate models/archive/20260720_120000 \
  --candidate models/archive/20260713_120000 \
  --json
```

Exit code `0` means every candidate passed. Exit code `1` means at least one
candidate is incompatible or has invalid metadata. Argument errors use
`argparse`'s standard exit code `2`.

The automated full-retraining workflow runs the same strict comparison after
metric evaluation and before promotion. Diagnostics are included in the
promotion reason, making missing, reordered, and type-changed columns actionable
without loading model binaries.

## Legacy metadata

Metadata created before feature contracts contains `feature_columns` but not
`feature_dtypes`. It remains comparable by name and order. Such results use
`validation_scope: names_only` and list `unchecked_dtypes`; retraining the model
regenerates metadata with the complete contract.
