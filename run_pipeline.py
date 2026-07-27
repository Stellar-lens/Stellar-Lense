"""Full LedgerLens detection pipeline entry point.

Usage:
    python run_pipeline.py --since 2024-01-01

Pipeline stages:
    1. Load historical trades per asset pair into a dict keyed by pair_id
    2. For each pair:
       a. Load order-book events (optional, skipped with ``--no-orderbook``)
       b. Load account activity and build the wallet funding graph (optional,
          skipped with ``--no-graph``)
       c. Build the per-wallet feature matrix
       d. Score each wallet with the trained ensemble (model_inference)
       e. Persist one RiskScore record per (wallet, pair_id) and optionally
          submit flagged wallets on-chain

Stage 2d requires trained models in `config.MODEL_DIR` — run
`detection/model_training.py` against a labelled dataset first. Until
models are trained, this script falls back to reporting Benford-only flags
(and persistence is skipped, since the `RiskScore` shape isn't available).

Checkpoint / resume
--------------------
Each asset pair is an independent unit of work (its own Horizon fetch,
feature build, and scoring pass). Pass ``--checkpoint-file`` to make a run
resumable: pairs already recorded as complete are skipped on the next
invocation, and a pair that raises is recorded as failed — logged and
retried on the next run — instead of aborting every other pair. Without
``--checkpoint-file`` the pipeline behaves exactly as before: a failure in
any pair propagates and aborts the run. See docs/checkpointing.md.
"""

import argparse
from datetime import UTC, datetime

import pandas as pd
from stellar_sdk import Asset as SdkAsset

from config import config
from detection.feature_engineering import build_feature_matrix
from detection.risk_score_store import RiskScoreStore
from detection.wallet_graph import build_funding_graph, detect_wash_trading_rings, ring_id_map
from ingestion.account_activity_loader import load_accounts_activity
from ingestion.historical_loader import (
    load_pair_to_dataframe,
)
from ingestion.orderbook_loader import load_accounts_orderbook_events
from utils.checkpoint import PipelineCheckpoint
from utils.logging import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LedgerLens detection pipeline")
    parser.add_argument(
        "--since",
        type=lambda s: datetime.fromisoformat(s),
        default=None,
        help="ISO date to start loading historical trades from (default: all available)",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip writing scored wallets to RISK_SCORE_DB_URL",
    )
    parser.add_argument(
        "--no-orderbook",
        action="store_true",
        help="Skip loading order-book events (faster, but order_cancellation_rate stays 0)",
    )
    parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Skip loading account activity and building the funding graph (faster, but "
        "funding_source_similarity and network_centrality stay 0)",
    )
    parser.add_argument(
        "--submit-onchain",
        action="store_true",
        help="Submit flagged wallets' RiskScore to the ledgerlens-score contract",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all pipeline stages but skip all writes (DB persist and on-chain submission).",
    )
    parser.add_argument(
        "--checkpoint-file",
        default=None,
        help="Path to a JSON checkpoint file enabling resumable per-pair processing. "
        "When set, pairs already recorded as complete are skipped and a pair that "
        "raises is recorded as failed (retried on the next --checkpoint-file run) "
        "instead of aborting the whole pipeline. Ignored with --dry-run.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Discard an existing --checkpoint-file and start over. No effect without "
        "--checkpoint-file.",
    )
    return parser.parse_args()


def _build_pair_specs(xlm: SdkAsset) -> list[tuple[str, SdkAsset]]:
    """Return the ordered ``(pair_id, base_asset)`` units of work for this run."""
    specs = []
    for code, issuer in config.WATCHED_ASSET_PAIRS:
        asset = xlm if issuer == "native" else SdkAsset(code, issuer)
        if asset == xlm:
            continue
        specs.append((f"{code}:{issuer}/XLM:native", asset))
    return specs


def _process_pair(
    pair_id: str,
    asset: SdkAsset,
    xlm: SdkAsset,
    args: argparse.Namespace,
    store: RiskScoreStore | None,
) -> pd.DataFrame:
    """Run stages 1–2e for a single asset pair and return its flagged-wallet rows.

    Raised exceptions propagate to the caller, which decides (based on whether
    checkpointing is enabled) whether to abort the whole run or record this
    pair as failed and continue with the rest.
    """
    logger.info("[pair=%s] Loading trades", pair_id)
    trades_df = load_pair_to_dataframe(asset, xlm, start_time=args.since)
    logger.info("[pair=%s] Loaded %d trades", pair_id, len(trades_df))

    if trades_df.empty:
        logger.info("[pair=%s] No trades — skipping", pair_id)
        return pd.DataFrame()

    wallets = list(pd.unique(trades_df[["base_account", "counter_account"]].values.ravel()))

    # --- Stage 2a: order-book events ---
    orderbook_events = None
    if not args.no_orderbook:
        logger.info("[pair=%s] Loading order-book events", pair_id)
        orderbook_events = load_accounts_orderbook_events(wallets)
        logger.info("[pair=%s] Loaded %d order-book events", pair_id, len(orderbook_events))

    # --- Stage 2b: funding graph ---
    funding_graph = None
    if not args.no_graph:
        logger.info("[pair=%s] Loading account activity and building funding graph", pair_id)
        activities = load_accounts_activity(wallets)
        funding_graph = build_funding_graph(activities)
        logger.info(
            "[pair=%s] Funding graph: %d nodes, %d edges",
            pair_id,
            funding_graph.number_of_nodes(),
            funding_graph.number_of_edges(),
        )

    # --- Stage 2c: feature matrix ---
    logger.info("[pair=%s] Building feature matrix", pair_id)
    feature_matrix = build_feature_matrix(
        trades_df, orderbook_events=orderbook_events, funding_graph=funding_graph
    )
    logger.info("[pair=%s] Built features for %d wallets", pair_id, len(feature_matrix))

    # --- Stage 2d: scoring ---
    logger.info("[pair=%s] Scoring wallets", pair_id)
    try:
        from detection.model_inference import RiskScorer

        scorer = RiskScorer()
        scored = scorer.score_matrix(feature_matrix)
    except (RuntimeError, ImportError) as exc:
        logger.warning("[pair=%s] Skipping ML scoring: %s", pair_id, exc)
        logger.warning("[pair=%s] Falling back to Benford-only flags", pair_id)
        mad_cols = [c for c in feature_matrix.columns if c.startswith("benford_mad_")]
        scored = feature_matrix[["wallet"] + mad_cols].copy()
        scored["benford_flag"] = (scored[mad_cols] > 0.015).any(axis=1)

    # --- Stage 2d.5: wash-trading ring id per wallet ---
    if funding_graph is not None and funding_graph.number_of_nodes() > 0:
        community_map = detect_wash_trading_rings(funding_graph)
        rid_map = ring_id_map(community_map, funding_graph)
    else:
        rid_map = {}
    scored["ring_id"] = [rid_map.get(w) for w in scored["wallet"]]

    # --- Stage 2e: persist + flag ---
    if "score" in scored:
        flagged = scored[scored["score"] >= config.RISK_SCORE_FLAG_THRESHOLD]

        if store is not None:
            for _, row in scored.iterrows():
                store.upsert(
                    wallet=row["wallet"],
                    asset_pair=pair_id,
                    risk_score={
                        "score": row["score"],
                        "benford_flag": row["benford_flag"],
                        "ml_flag": row["ml_flag"],
                        "confidence": row["confidence"],
                        "ring_id": row.get("ring_id"),
                    },
                )
            logger.info("[pair=%s] Persisted %d scored wallets", pair_id, len(scored))
    else:
        flagged = scored[scored["benford_flag"]]

    logger.info("[pair=%s] Flagged wallets (%d):\n%s", pair_id, len(flagged), flagged)

    if args.submit_onchain:
        if args.dry_run:
            logger.warning("[pair=%s] [DRY RUN] Skipping on-chain submission", pair_id)
        elif "score" not in scored:
            logger.warning(
                "[pair=%s] Skipping on-chain submission: no ML scores available", pair_id
            )
        else:
            submit_flagged_onchain(flagged, pair_id)

    return flagged


def main() -> None:
    config.validate()
    args = parse_args()

    if args.dry_run:
        logger.info("[DRY RUN] No data will be written.")

    xlm = SdkAsset.native()
    pair_specs = _build_pair_specs(xlm)

    if not pair_specs:
        logger.warning("No pairs configured or all pairs skipped.")
        return

    checkpoint: PipelineCheckpoint | None = None
    if args.checkpoint_file and not args.dry_run:
        checkpoint = PipelineCheckpoint.load_or_create(
            path=args.checkpoint_file,
            pipeline="run_pipeline",
            fingerprint_inputs={
                "since": args.since.isoformat() if args.since else None,
                "pairs": sorted(pair_id for pair_id, _ in pair_specs),
                "no_orderbook": args.no_orderbook,
                "no_graph": args.no_graph,
            },
            fresh=args.fresh,
        )
    elif args.checkpoint_file and args.dry_run:
        logger.warning("--checkpoint-file has no effect with --dry-run — ignoring")

    pending_ids = (
        set(checkpoint.pending([pair_id for pair_id, _ in pair_specs]))
        if checkpoint is not None
        else None
    )
    pending_specs = (
        pair_specs if pending_ids is None else [s for s in pair_specs if s[0] in pending_ids]
    )

    logger.info(
        "[1] Processing %d/%d pair(s): %s",
        len(pending_specs),
        len(pair_specs),
        [pair_id for pair_id, _ in pending_specs],
    )

    all_flagged: list[pd.DataFrame] = []
    store = RiskScoreStore() if not args.no_persist and not args.dry_run else None

    for pair_id, asset in pending_specs:
        logger.info("[pair=%s] Processing", pair_id)

        if checkpoint is None:
            flagged = _process_pair(pair_id, asset, xlm, args, store)
            all_flagged.append(flagged)
            continue

        try:
            flagged = _process_pair(pair_id, asset, xlm, args, store)
        except Exception as exc:
            logger.exception("[pair=%s] Failed — recording for retry on next --resume", pair_id)
            checkpoint.record_failure(pair_id, exc)
            continue

        checkpoint.record_success(pair_id, metadata={"flagged": len(flagged)})
        all_flagged.append(flagged)

    if checkpoint is not None:
        summary = checkpoint.summary()
        logger.info(
            "[checkpoint] Run summary: %d completed, %d failed (%s)",
            summary["completed"],
            len(summary["failed"]),
            summary["failed"] or "none",
        )

    combined_flagged = pd.concat(all_flagged, ignore_index=True) if all_flagged else pd.DataFrame()
    logger.info("Total flagged wallets across all pairs: %d", len(combined_flagged))


def submit_flagged_onchain(flagged: pd.DataFrame, pair_id: str) -> None:
    """Submit each flagged wallet's `RiskScore` to the `ledgerlens-score` contract."""
    from integrations.contract_client import LedgerLensContractClient

    client = LedgerLensContractClient()
    timestamp = int(datetime.now(UTC).timestamp())

    for _, row in flagged.iterrows():
        risk_score = {
            "score": int(row["score"]),
            "benford_flag": bool(row["benford_flag"]),
            "ml_flag": bool(row["ml_flag"]),
            "timestamp": timestamp,
            "confidence": int(row["confidence"]),
        }
        client.submit_score(wallet=row["wallet"], asset_pair=pair_id, risk_score=risk_score)

    logger.info("      Submitted %d RiskScores on-chain for %s", len(flagged), pair_id)


if __name__ == "__main__":
    main()
