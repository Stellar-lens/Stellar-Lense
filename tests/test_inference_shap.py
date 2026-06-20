import pytest

from detection.model_inference import RiskScorer
from detection.model_training import save_models, train_models
from detection.shap_explainer import ShapExplainer
from scripts.generate_synthetic_dataset import generate_synthetic_dataset


@pytest.fixture(scope="module")
def trained_models(tmp_path_factory):
    df = generate_synthetic_dataset(n_wallets=60, seed=2)
    results = train_models(df, test_size=0.3, random_state=2)
    model_dir = str(tmp_path_factory.mktemp("models"))
    save_models(results, model_dir)
    return results, model_dir, df


def test_risk_scorer_score_returns_contract_shape(trained_models):
    _, model_dir, df = trained_models
    scorer = RiskScorer(model_dir=model_dir)

    row = df.drop(columns=["label"]).iloc[0]
    result = scorer.score(row)

    required = {"score", "benford_flag", "ml_flag", "confidence"}
    assert required.issubset(set(result))
    assert 0 <= result["score"] <= 100
    assert 0 <= result["confidence"] <= 100
    assert isinstance(result["benford_flag"], bool)
    assert isinstance(result["ml_flag"], bool)


def test_risk_scorer_score_matrix(trained_models):
    _, model_dir, df = trained_models
    scorer = RiskScorer(model_dir=model_dir)

    features = df.drop(columns=["label"])
    scored = scorer.score_matrix(features)

    assert "wallet" in scored.columns
    assert {"score", "benford_flag", "ml_flag", "confidence"}.issubset(set(scored.columns))
    assert len(scored) == len(features)


def test_risk_scorer_raises_without_models(tmp_path):
    scorer = RiskScorer(model_dir=str(tmp_path))
    with pytest.raises(RuntimeError):
        scorer.score(
            generate_synthetic_dataset(n_wallets=2, seed=3).drop(columns=["label"]).iloc[0]
        )


def test_shap_explainer_explain(trained_models):
    results, _, df = trained_models
    model = results["random_forest"]["model"]
    explainer = ShapExplainer(model)

    row = df.drop(columns=["label"]).iloc[0]
    explanation = explainer.explain(row, top_n=3)

    assert len(explanation) == 3
    for entry in explanation:
        assert set(entry) == {"feature", "contribution", "value"}


def test_shap_explainer_explain_ensemble(trained_models):
    results, _, df = trained_models
    models = {name: result["model"] for name, result in results.items()}
    explainer = ShapExplainer()

    row = df.drop(columns=["label"]).iloc[0]
    explanation = explainer.explain_ensemble(row, models, top_n=3)

    assert len(explanation) == 3
    for entry in explanation:
        assert set(entry) == {"feature", "contribution", "value"}
