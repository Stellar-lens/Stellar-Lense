## Summary

What does this PR change and why?

## Type of change

<!-- Check all that apply -->
- [ ] Bug fix
- [ ] New feature
- [ ] Data/schema change (affects feature columns, data models, Avro schema)
- [ ] Model change (affects training, inference, or evaluation metrics)
- [ ] Infrastructure / CI change
- [ ] Documentation only
- [ ] Security fix

## Changelog

<!-- REQUIRED: paste the entry you added to CHANGELOG.md under [Unreleased] -->
<!-- If this PR touches detection/feature_engineering.py, detection/model_*.py, -->
<!-- ingestion/data_models.py, data/*, or models/* an entry is mandatory.       -->

```
### Added / Changed / Fixed / ...
- <your entry here>
```

## Impact assessment

### Data / feature schema changes
<!-- If feature_engineering.py, data_models.py, or data/trade_avro_schema.json changed: -->
- [ ] No schema changes
- [ ] New feature columns added (update data/feature_dictionary.md)
- [ ] Feature columns removed or renamed (update feature_schema_hash; note downstream impact)
- [ ] Avro schema evolved (backward-compatible / breaking)

### Model changes
<!-- If model_training.py, model_inference.py, or models/* changed: -->
- [ ] No model changes
- [ ] Model retrained — include before/after AUC-ROC / F1 in the summary above
- [ ] Inference API changed — update ledgerlens-core if RiskScore shape changed
- [ ] Feature schema hash will change — all consumers need to reload models

### Downstream impact
<!-- Check any systems affected by this change -->
- [ ] `ledgerlens-api` — REST API response shape may change
- [ ] `ledgerlens-dashboard` — visualization or SHAP field names may change
- [ ] `ledgerlens-contract` — on-chain RiskScore struct may change
- [ ] `ledgerlens-core` — shared types or thresholds may change
- [ ] None

## Checklist

- [ ] `make test` passes locally
- [ ] `make lint` and `make format` are clean
- [ ] New/changed behavior has test coverage
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] If a shared contract changed (`RiskScore`, asset pair format, feature
      schema), linked issues/PRs in `ledgerlens-core` and downstream repos
- [ ] `data/feature_dictionary.md` updated if feature columns added/removed
- [ ] Model metrics (AUC/F1) documented if models were retrained
- [ ] Security review requested if touching `detection/privacy/`,
      `detection/adversarial/`, `utils/field_encryption.py`, or
      `detection/audit_trail.py`
