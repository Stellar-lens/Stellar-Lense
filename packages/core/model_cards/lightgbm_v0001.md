# Lightgbm - Version v0001

*Generated on: 2026-09-11T13:08:55.171056+00:00*

## Model Details

- **Model Name**: lightgbm
- **Version**: v0001
- **Trained At**: 2026-09-11T13:08:55.170955+00:00

## Intended Use

This model is intended to detect wash trading activity on Stellar DEXs, using behavioral features, Benford's Law analysis, and SHAP values for interpretability.

## Out of Scope Uses

- Use as a sole decision-making tool for regulatory enforcement without human review
- Use on non-Stellar blockchains without retraining
- Use for real-time blocking of trades without additional safeguards

## Metrics

| Metric | Value |
|--------|-------|
| Auc Roc | 0.8600 |

## Top Features (SHAP)

| Rank | Feature | Mean Absolute SHAP |
|------|---------|--------------------|

## Datasheet for Datasets

- **Source**: ingestion.synthetic_data
- **Number of Samples**: 90
- **Feature Count**: 122
- **Imbalance Strategy**: SMOTE

### Class Balance (Pre-SMOTE)

| Class | Proportion |
|-------|------------|
| 0 | 66.67% |
| 1 | 33.33% |

## Known Limitations

- Model performance may degrade under heavy adversarial evasion
- Requires sufficient trade history (minimum 10 trades recommended)
- Not validated for use outside of Stellar DEXs