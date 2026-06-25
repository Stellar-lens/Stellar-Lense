"""Repository for reading and writing `RiskScoreRecord`s.

Used by `run_pipeline.py` to persist `RiskScorer.score()` output for
`ledgerlens-api` to read, and to look up previously flagged wallets.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from detection.persistence import RiskScoreRecord, ShapQueryCount, get_session_factory


class RiskScoreStore:
    """CRUD wrapper around `RiskScoreRecord` keyed by `(wallet, asset_pair)`."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None):
        self._session_factory = session_factory or get_session_factory()

    def upsert(self, wallet: str, asset_pair: str, risk_score: dict) -> RiskScoreRecord:
        """Insert or update the `RiskScore` record for `(wallet, asset_pair)`.

        `risk_score` is the dict returned by `RiskScorer.score()`:
        `{"score", "benford_flag", "ml_flag", "confidence"}` (and optionally
        `"timestamp"`, which is ignored — `updated_at` is set server-side).
        """
        with self._session_factory() as session:
            existing = session.scalar(
                select(RiskScoreRecord).where(
                    RiskScoreRecord.wallet == wallet,
                    RiskScoreRecord.asset_pair == asset_pair,
                )
            )
            if existing is None:
                existing = RiskScoreRecord(wallet=wallet, asset_pair=asset_pair)
                session.add(existing)

            existing.score = int(risk_score["score"])
            existing.benford_flag = bool(risk_score["benford_flag"])
            existing.ml_flag = bool(risk_score["ml_flag"])
            existing.confidence = int(risk_score["confidence"])

            session.commit()
            session.refresh(existing)
            return existing

    def get(self, wallet: str, asset_pair: str) -> RiskScoreRecord | None:
        with self._session_factory() as session:
            return session.scalar(
                select(RiskScoreRecord).where(
                    RiskScoreRecord.wallet == wallet,
                    RiskScoreRecord.asset_pair == asset_pair,
                )
            )

    def list_flagged(self, threshold: int) -> Iterable[RiskScoreRecord]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(RiskScoreRecord)
                    .where(RiskScoreRecord.score >= threshold)
                    .order_by(RiskScoreRecord.score.desc())
                )
            )

    # ------------------------------------------------------------------
    # SHAP query accounting (differential-privacy Rényi composition)
    # ------------------------------------------------------------------

    def increment_shap_query(self, wallet: str) -> int:
        """Atomically increment and return `wallet`'s SHAP query count."""
        with self._session_factory() as session:
            counter = session.get(ShapQueryCount, wallet)
            if counter is None:
                counter = ShapQueryCount(wallet=wallet, query_count=0)
                session.add(counter)
            counter.query_count += 1
            new_count = counter.query_count
            session.commit()
            return new_count

    def get_shap_query_count(self, wallet: str) -> int:
        """Return `wallet`'s current SHAP query count (0 if never queried)."""
        with self._session_factory() as session:
            counter = session.get(ShapQueryCount, wallet)
            return counter.query_count if counter is not None else 0
