"""SHAP-based interpretability for risk scores.

Wraps each trained ensemble model with a SHAP explainer so that every
risk score can be accompanied by a per-feature attribution, surfaced via
the API for auditors and end-users.
"""

import pandas as pd
import shap

from detection.model_training import FEATURE_COLUMNS_EXCLUDE


class ShapExplainer:
    """Produces SHAP value explanations for one or more trained models.

    `TreeExplainer` construction is not free, so explainers are cached per
    model id (`id(model)`) and reused across calls.
    """

    def __init__(self, model=None):
        self._explainers: dict[int, shap.TreeExplainer] = {}
        self.model = model
        if model is not None:
            self.explainer = self._get_explainer(model)

    def _get_explainer(self, model) -> shap.TreeExplainer:
        key = id(model)
        if key not in self._explainers:
            self._explainers[key] = shap.TreeExplainer(model)
        return self._explainers[key]

    def _shap_values_for(self, model, X: pd.DataFrame):
        explainer = self._get_explainer(model)
        shap_values = explainer.shap_values(X)
        # Binary classifiers may return a list [class_0, class_1]
        return shap_values[1][0] if isinstance(shap_values, list) else shap_values[0]

    def explain(self, feature_row: pd.Series, top_n: int = 5, model=None) -> list[dict]:
        """Return the top `top_n` features driving this wallet's score
        according to a single model.

        Each entry: {"feature": str, "contribution": float, "value": float}
        """
        model = model or self.model
        if model is None:
            raise ValueError("No model provided to explain()")

        feature_cols = [c for c in feature_row.index if c not in FEATURE_COLUMNS_EXCLUDE]
        X = feature_row[feature_cols].to_frame().T

        values = self._shap_values_for(model, X)

        contributions = sorted(
            zip(feature_cols, values, X.iloc[0].values, strict=True),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:top_n]

        return [
            {"feature": name, "contribution": float(value), "value": float(raw)}
            for name, value, raw in contributions
        ]

    def explain_ensemble(self, feature_row: pd.Series, models: dict, top_n: int = 5) -> list[dict]:
        """Aggregate per-model SHAP contributions across an ensemble into a
        single ranked list.

        `models` maps model name -> fitted estimator (e.g. the `MODEL_REGISTRY`
        models loaded by `RiskScorer`). Contributions for each feature are
        averaged across models, then sorted by absolute magnitude.

        Each entry: {"feature": str, "contribution": float, "value": float}
        """
        if not models:
            raise ValueError("No models provided to explain_ensemble()")

        feature_cols = [c for c in feature_row.index if c not in FEATURE_COLUMNS_EXCLUDE]
        X = feature_row[feature_cols].to_frame().T
        raw_values = X.iloc[0].values

        totals = [0.0] * len(feature_cols)
        for model in models.values():
            values = self._shap_values_for(model, X)
            for i, value in enumerate(values):
                totals[i] += float(value)

        averaged = [total / len(models) for total in totals]

        contributions = sorted(
            zip(feature_cols, averaged, raw_values, strict=True),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:top_n]

        return [
            {"feature": name, "contribution": float(value), "value": float(raw)}
            for name, value, raw in contributions
        ]
