from datetime import datetime

import pandas as pd

from detection.feature_engineering import compute_wallet_graph_features
from detection.wallet_graph import (
    build_funding_graph,
    compute_wallet_graph_metrics,
    funding_source_similarity,
    network_centrality,
)
from ingestion.data_models import AccountActivity


def sample_activities() -> list[AccountActivity]:
    return [
        AccountActivity(account_id="F", account_created_at=datetime(2020, 1, 1)),
        AccountActivity(
            account_id="A", account_created_at=datetime(2021, 1, 1), funding_account="F"
        ),
        AccountActivity(
            account_id="B", account_created_at=datetime(2021, 1, 2), funding_account="F"
        ),
        AccountActivity(account_id="C", account_created_at=datetime(2021, 1, 3)),
    ]


def test_build_funding_graph_edges():
    graph = build_funding_graph(sample_activities())
    assert set(graph.nodes) == {"F", "A", "B", "C"}
    assert ("F", "A") in graph.edges
    assert ("F", "B") in graph.edges


def test_funding_source_similarity_shared_funder():
    graph = build_funding_graph(sample_activities())
    # A and B share the same funding ancestor (F) -> similarity 1.0
    assert funding_source_similarity("A", graph) == 1.0
    assert funding_source_similarity("B", graph) == 1.0


def test_funding_source_similarity_no_ancestors():
    graph = build_funding_graph(sample_activities())
    assert funding_source_similarity("F", graph) == 0.0
    assert funding_source_similarity("C", graph) == 0.0


def test_funding_source_similarity_wallet_not_in_graph():
    graph = build_funding_graph(sample_activities())
    assert funding_source_similarity("Z", graph) == 0.0


def test_network_centrality_ranks_funder_highest():
    graph = build_funding_graph(sample_activities())
    assert network_centrality("F", graph) > network_centrality("A", graph)


def test_compute_wallet_graph_metrics_shape():
    graph = build_funding_graph(sample_activities())
    metrics = compute_wallet_graph_metrics("A", graph)
    assert set(metrics) == {"funding_source_similarity", "network_centrality"}


def test_compute_wallet_graph_features_without_graph_defaults_to_zero():
    activity = AccountActivity(account_id="A", account_created_at=datetime(2021, 1, 1))
    features = compute_wallet_graph_features("A", activity, pd.Timestamp.now(tz="UTC"))
    assert features["funding_source_similarity"] == 0.0
    assert features["network_centrality"] == 0.0


def test_compute_wallet_graph_features_with_graph():
    graph = build_funding_graph(sample_activities())
    activity = AccountActivity(
        account_id="A", account_created_at=datetime(2021, 1, 1), funding_account="F"
    )
    features = compute_wallet_graph_features("A", activity, pd.Timestamp.now(tz="UTC"), graph)
    assert features["funding_source_similarity"] == 1.0
    assert features["network_centrality"] > 0.0
