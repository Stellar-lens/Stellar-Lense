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

Also provides:

- `build_co_trade_graph`: builds edges between wallets that co-traded the
  same asset pair within a configurable time window.
"""

import re
import warnings
from collections.abc import Iterable
from typing import Optional

import networkx as nx
import pandas as pd

from ingestion.data_models import AccountActivity

# Stellar account ID format: G followed by 55 uppercase base-32 chars
_STELLAR_ACCOUNT_RE = re.compile(r"^G[A-Z2-7]{55}$")


def _validate_account_id(account_id: str) -> bool:
    """Return True if *account_id* matches the Stellar account ID format."""
    return bool(_STELLAR_ACCOUNT_RE.match(account_id))


def build_funding_graph(
    activities: Iterable[AccountActivity],
    validate_account_ids: bool = False,
) -> nx.DiGraph:
    """Build a directed graph with edges ``funding_account -> account_id``.

    Parameters
    ----------
    activities:
        Iterable of :class:`~ingestion.data_models.AccountActivity` records.
    validate_account_ids:
        When ``True``, edges where either endpoint does not match the Stellar
        account ID format (``^G[A-Z2-7]{55}$``) are silently dropped.  Set
        this to ``True`` when feeding data directly from the Horizon API.
        Defaults to ``False`` for backwards compatibility with test fixtures
        that use short synthetic identifiers.
    """
    graph: nx.DiGraph = nx.DiGraph()
    for activity in activities:
        if validate_account_ids and not _validate_account_id(activity.account_id):
            continue
        graph.add_node(activity.account_id)
        if activity.funding_account:
            if validate_account_ids and not _validate_account_id(activity.funding_account):
                continue
            graph.add_edge(
                activity.funding_account,
                activity.account_id,
                edge_type="funding",
                weight=1,
            )
    return graph


def build_co_trade_graph(
    trades_df: pd.DataFrame,
    window_hours: int,
) -> nx.DiGraph:
    """Build a directed co-trade graph from a trades DataFrame.

    Two wallets get a bidirectional ``co_trade`` edge when both traded the
    same asset pair within *window_hours* of each other.

    Parameters
    ----------
    trades_df:
        DataFrame produced by the ingestion layer.  Must contain columns:
        ``base_account``, ``counter_account``, ``base_asset``,
        ``counter_asset``, ``ledger_close_time``, ``amount``.
    window_hours:
        Maximum time difference (in hours) between two trades on the same
        pair for the wallets to receive a co-trade edge.

    Returns
    -------
    nx.DiGraph
        Nodes are wallet addresses.  Edges carry:
        - ``edge_type = "co_trade"``
        - ``weight``   – number of co-trade events observed
        - ``timestamp`` – first observed co-trade timestamp (ISO string)

    Notes
    -----
    Both endpoints of every edge are validated against the Stellar account-ID
    regex; invalid IDs are silently dropped.
    """
    graph: nx.DiGraph = nx.DiGraph()

    if trades_df.empty:
        return graph

    required_cols = {
        "base_account",
        "counter_account",
        "base_asset",
        "counter_asset",
        "ledger_close_time",
        "amount",
    }
    if not required_cols.issubset(trades_df.columns):
        return graph

    df = trades_df.copy()
    df["ledger_close_time"] = pd.to_datetime(df["ledger_close_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["ledger_close_time"])

    # Canonical pair identifier: sort the two asset legs alphabetically
    df["pair_id"] = df.apply(
        lambda r: "/".join(sorted([str(r["base_asset"]), str(r["counter_asset"])])),
        axis=1,
    )

    # Collect all wallets observed per (pair_id, time-bucket) grouped by window
    window_td = pd.Timedelta(hours=window_hours)

    # For each pair, find wallets that traded within the same window
    for pair_id, pair_df in df.groupby("pair_id"):
        pair_df = pair_df.sort_values("ledger_close_time")

        # Collect (wallet, timestamp) pairs — each trade contributes both sides
        events: list[tuple[str, pd.Timestamp]] = []
        for _, row in pair_df.iterrows():
            for acct in (row["base_account"], row["counter_account"]):
                if _validate_account_id(str(acct)):
                    events.append((str(acct), row["ledger_close_time"]))

        if len(events) < 2:
            continue

        # Sliding window: for each event find all other wallets within the window
        events.sort(key=lambda x: x[1])
        for i, (wallet_a, time_a) in enumerate(events):
            for j in range(i + 1, len(events)):
                wallet_b, time_b = events[j]
                if time_b - time_a > window_td:
                    break
                if wallet_a == wallet_b:
                    continue

                # Add/update bidirectional edge
                for src, dst in [(wallet_a, wallet_b), (wallet_b, wallet_a)]:
                    if graph.has_edge(src, dst):
                        graph[src][dst]["weight"] += 1
                    else:
                        graph.add_edge(
                            src,
                            dst,
                            edge_type="co_trade",
                            weight=1,
                            timestamp=time_a.isoformat(),
                        )

    return graph


# ---------------------------------------------------------------------------
# Legacy feature functions — kept for backwards compatibility with existing
# tests and the model artifact. New code should use GNNEncoder embeddings.
# ---------------------------------------------------------------------------


def funding_source_similarity(wallet: str, graph: nx.DiGraph) -> float:
    """Highest Jaccard similarity between ``wallet``'s funding ancestors and
    any other node's funding ancestors in ``graph``.

    Returns ``0.0`` if ``wallet`` isn't in the graph or has no funding
    ancestors.

    .. deprecated::
        Use :class:`detection.gnn_encoder.GNNEncoder` embeddings instead.
        This scalar feature is preserved for backwards compatibility with the
        existing model artifact.
    """
    warnings.warn(
        "funding_source_similarity is deprecated; use GNNEncoder embeddings instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _funding_source_similarity(wallet, graph)


def _funding_source_similarity(wallet: str, graph: nx.DiGraph) -> float:
    """Internal (non-deprecated) implementation used by compute_wallet_graph_metrics."""
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
    """Degree centrality of ``wallet`` within the funding graph.

    .. deprecated::
        Use :class:`detection.gnn_encoder.GNNEncoder` embeddings instead.
        This scalar feature is preserved for backwards compatibility with the
        existing model artifact.
    """
    warnings.warn(
        "network_centrality is deprecated; use GNNEncoder embeddings instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _network_centrality(wallet, graph)


def _network_centrality(wallet: str, graph: nx.DiGraph) -> float:
    """Internal (non-deprecated) implementation used by compute_wallet_graph_metrics."""
    if wallet not in graph or graph.number_of_nodes() < 2:
        return 0.0
    return float(nx.degree_centrality(graph)[wallet])


def compute_wallet_graph_metrics(wallet: str, graph: nx.DiGraph) -> dict:
    """Return ``{funding_source_similarity, network_centrality}`` for *wallet*.

    Calls the internal implementations directly to avoid emitting deprecation
    warnings from internal code paths.
    """
    return {
        "funding_source_similarity": _funding_source_similarity(wallet, graph),
        "network_centrality": _network_centrality(wallet, graph),
    }
