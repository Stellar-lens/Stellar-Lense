"""Full LedgerLens detection pipeline entry point.

Usage:
    python run_pipeline.py --since 2024-01-01

Pipeline stages:
    1. Load historical trades for all watched asset pairs (ingestion)
    2. Build the per-wallet feature matrix (Benford + ML features)
    3. Score each wallet with the trained ensemble (model_inference)
    4. Output flagged wallets above `config.RISK_SCORE_FLAG_THRESHOLD`

Stage 3 requires trained models in `config.MODEL_DIR` — run
`detection/model_training.py` against a labelled dataset first. Until
models are trained, this script falls back to reporting Benford-only flags.
"""

import argparse
from datetime import datetime

from config import config
from detection.feature_engineering import build_feature_matrix
from ingestion.historical_loader import load_watched_pairs_to_dataframe
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logger.info("[1/3] Loading trades for watched pairs: %s", config.WATCHED_ASSET_PAIRS)
    trades_df = load_watched_pairs_to_dataframe(start_time=args.since)
    logger.info("      Loaded %d trades", len(trades_df))

    logger.info("[2/3] Building feature matrix")
    feature_matrix = build_feature_matrix(trades_df)
    logger.info("      Built features for %d wallets", len(feature_matrix))

    logger.info("[3/3] Scoring wallets")
    try:
        from detection.model_inference import RiskScorer

        scorer = RiskScorer()
        scored = scorer.score_matrix(feature_matrix)
    except (RuntimeError, ImportError) as exc:
        logger.warning("      Skipping ML scoring: %s", exc)
        logger.warning("      Falling back to Benford-only flags")
        mad_cols = [c for c in feature_matrix.columns if c.startswith("benford_mad_")]
        scored = feature_matrix[["wallet"] + mad_cols].copy()
        scored["benford_flag"] = (scored[mad_cols] > 0.015).any(axis=1)

    if "score" in scored:
        flagged = scored[scored["score"] >= config.RISK_SCORE_FLAG_THRESHOLD]
    else:
        flagged = scored[scored["benford_flag"]]

    logger.info("Flagged wallets (%d):\n%s", len(flagged), flagged)


if __name__ == "__main__":
    main()
