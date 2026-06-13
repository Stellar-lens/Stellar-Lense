"""Wallet funding-graph features: `funding_source_similarity` and
`network_centrality`.

Builds a directed graph of "funded by" relationships from
`AccountActivity.funding_account` and derives two signals used by
`feature_engineering.compute_wallet_graph_features`:

- `funding_source_similarity`: the highest Jaccard similarity between a
  wallet's set of funding ancestors and any other wallet's funding-ancestor
  set. A high value means two wallets trace back to the same funding
  source(s) — a common pattern for sock-puppet / wash-trading rings.
- `network_centrality`: degree centrality of the wallet within the funding
  graph, a proxy for how connected/influential an account is within the
  observed funding network.
"""

from collections.abc import Iterable

import networkx as nx

from ingestion.data_models import AccountActivity


def build_funding_graph(activities: Iterable[AccountActivity]) -> nx.DiGraph:
    """Build a directed graph with edges `funding_account -> account_id`."""
    graph: nx.DiGraph = nx.DiGraph()
    for activity in activities:
        graph.add_node(activity.account_id)
        if activity.funding_account:
            graph.add_edge(activity.funding_account, activity.account_id)
    return graph


def funding_source_similarity(wallet: str, graph: nx.DiGraph) -> float:
    """Highest Jaccard similarity between `wallet`'s funding ancestors and
    any other node's funding ancestors in `graph`.

    Returns `0.0` if `wallet` isn't in the graph or has no funding ancestors.
    """
    if wallet not in graph:
        return 0.0

    wallet_ancestors = nx.ancestors(graph, wallet)
    if not wallet_ancestors:
        return 0.0

    best = 0.0
    for other in graph.nodes:
        if other == wallet:
            continue
        other_ancestors = nx.ancestors(graph, other)
        if not other_ancestors:
            continue
        union = wallet_ancestors | other_ancestors
        if not union:
            continue
        jaccard = len(wallet_ancestors & other_ancestors) / len(union)
        best = max(best, jaccard)

    return float(best)


def network_centrality(wallet: str, graph: nx.DiGraph) -> float:
    """Degree centrality of `wallet` within the funding graph."""
    if wallet not in graph or graph.number_of_nodes() < 2:
        return 0.0
    return float(nx.degree_centrality(graph)[wallet])


def compute_wallet_graph_metrics(wallet: str, graph: nx.DiGraph) -> dict:
    """Return `{funding_source_similarity, network_centrality}` for `wallet`."""
    return {
        "funding_source_similarity": funding_source_similarity(wallet, graph),
        "network_centrality": network_centrality(wallet, graph),
    }
