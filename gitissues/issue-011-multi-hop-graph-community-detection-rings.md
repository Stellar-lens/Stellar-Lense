# Implement Multi-Hop Funding Graph with Community Detection for Wash-Trading Ring Identification

**Label:** `advanced` | `detection` | `graph-analysis` | `research`
**Difficulty:** Advanced
**Area:** `detection/wallet_graph.py`, `ingestion/`, `detection/feature_engineering.py`

---

## Summary

The current `detection/wallet_graph.py` implements `funding_source_similarity` (Jaccard similarity of funding ancestors) and `network_centrality` (degree centrality). Both are single-hop metrics: they look at immediate funding relationships.

Real wash-trading rings on the Stellar DEX use **multi-hop obfuscation**: the controlling wallet creates intermediate accounts that create the actual trading wallets, inserting 2–4 hops between the controller and the traders. Single-hop metrics miss these rings entirely.

This issue asks you to:
1. Extend the funding graph to support **recursive, multi-hop ancestor traversal** (up to a configurable depth limit).
2. Apply **graph community detection** (Louvain algorithm or spectral clustering on the adjacency matrix) to identify clusters of wallets that likely belong to the same wash-trading ring.
3. Introduce **ring membership** as a new binary feature in the feature vector: `in_wash_trading_ring` (bool) and `ring_size` (int: size of the detected community).
4. Add a `ring_id` column to the scored output so the API and dashboard can group wallets by ring.

---

## Detailed Description

### Part 1: Multi-hop ancestor traversal (`detection/wallet_graph.py`)

Replace the current `nx.ancestors()` call in `funding_source_similarity` with a **BFS/DFS up to `max_depth` hops** (default: 4). The current implementation already uses `nx.ancestors()` which traverses all reachable predecessors, but the graph must be populated with multi-hop edges from the account activity loader (Issue #005) to have depth > 1.

Extend `build_funding_graph` to accept a `max_depth: int` parameter that caps BFS traversal when building the subgraph. This prevents runaway graph expansion on large, highly-connected networks and lets callers control the computational cost.

### Part 2: Community detection (`detection/wallet_graph.py`)

Add `detect_wash_trading_rings(graph: nx.DiGraph, resolution: float = 1.0) -> dict[str, int]`:
- Convert the funding graph to an undirected graph for community detection.
- Apply the **Louvain community detection algorithm** (`python-louvain` / `community` package, or `networkx`'s `greedy_modularity_communities` as a fallback).
- Return a dict mapping `wallet_id -> community_id`.
- Communities with fewer than `min_ring_size` (default: 3) members are not considered rings; their wallets are assigned `community_id = -1` (no ring).

Add `ring_statistics(community_id: int, community_map: dict[str, int], graph: nx.DiGraph) -> dict`:
- Returns `{ring_id, ring_size, internal_edge_density, avg_funding_depth}` for a given community.
- `internal_edge_density` is the fraction of possible edges within the community that actually exist — a measure of how tightly connected the ring is.

### Part 3: New feature columns (`detection/feature_engineering.py`)

Add to `compute_wallet_graph_features`:
- `in_wash_trading_ring` (bool): `community_id != -1`.
- `ring_size` (int): size of the detected community (0 if not in a ring).
- `ring_internal_density` (float): the ring's internal edge density (0.0 if not in a ring).

These require `community_map` and `ring_stats` to be passed down from `build_feature_matrix` — extend the function signature accordingly.

### Part 4: `ring_id` in scored output (`run_pipeline.py`, `detection/risk_score_store.py`)

- Add `ring_id: str | None` (the community ID as a stable string, e.g. `"ring_<hash_of_member_set>"`) to the scored output DataFrame and to `RiskScoreRecord`.
- This requires a migration: add `ring_id` column to the `risk_scores` table as a nullable string. Use SQLAlchemy's `Alembic` or a plain `ALTER TABLE` migration script.

### Package dependency

Add `python-louvain` (community detection) to `requirements.txt`.

---

## Requirements

### Functional
- Multi-hop traversal must not visit more than `max_depth` hops from the seed wallet.
- Community detection must be deterministic: same graph → same community assignments (Louvain is non-deterministic by default; use a fixed seed).
- `in_wash_trading_ring = True` only when `ring_size >= min_ring_size`.
- The DB migration must be backward-compatible: existing rows get `ring_id = NULL`.

### Performance
- BFS traversal with `max_depth=4` on a graph of 10,000 nodes must complete in < 2 seconds (benchmark in a test using `time.monotonic`).
- Community detection on a graph of 10,000 nodes must complete in < 30 seconds.

### Correctness
- Louvain community detection seed must be fixed so CI tests are reproducible.

### Security
- No new credentials required.

### Documentation
- Add a "Wallet Graph Features" subsection to `README.md` describing multi-hop traversal, community detection methodology, and the new features.
- Document the `ring_id` field in the "Shared Contracts / RiskScore" section.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_wallet_graph_advanced.py`:

1. **`test_multi_hop_ancestor_traversal_depth_1`** — graph `A→B→C→D`; with `max_depth=1`, ancestors of `D` = `{C}` only.
2. **`test_multi_hop_ancestor_traversal_depth_3`** — same graph, `max_depth=3`; ancestors of `D` = `{A, B, C}`.
3. **`test_community_detection_identifies_ring`** — construct a graph with a tight cluster of 5 wallets (all funded by the same source) plus 2 isolated wallets; assert the 5 wallets share a `community_id != -1` and the 2 isolates get `community_id = -1`.
4. **`test_community_detection_is_deterministic`** — run `detect_wash_trading_rings` twice on the same graph; assert identical `community_id` assignments both times.
5. **`test_ring_size_feature_nonzero_in_cluster`** — given a 5-wallet ring, assert `ring_size = 5` in each member's feature vector.
6. **`test_small_cluster_excluded_from_rings`** — a pair of wallets (size 2) with `min_ring_size=3`; assert both get `in_wash_trading_ring = False` and `ring_size = 0`.
7. **`test_ring_internal_density`** — complete subgraph of 4 nodes (6 undirected edges out of 6 possible); assert `ring_internal_density ≈ 1.0`.
8. **`test_bfs_performance_10k_nodes`** — generate a random graph with 10,000 nodes; assert BFS with `max_depth=4` completes in < 2 seconds.

Run with: `pytest tests/test_wallet_graph_advanced.py -v`

All eight tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Graph theory / network analysis / Python ML engineering. Deep familiarity with `networkx`, graph algorithms (BFS/DFS, Louvain modularity, spectral methods), and feature engineering for ML is required. Experience with blockchain forensics or social network analysis is a strong plus.

When commenting to claim this issue, please include:
- Your experience with graph algorithms and community detection methods.
- Whether you have worked with `networkx` or alternative graph libraries (`igraph`, `graph-tool`).
- A brief note on your preferred community detection algorithm and why (Louvain vs. Leiden vs. label propagation).
- Any prior work on fraud ring detection, social network analysis, or anti-money-laundering systems.

This issue adds a fundamentally new detection dimension: topological ring identification that cannot be evaded by changing individual trading patterns.
