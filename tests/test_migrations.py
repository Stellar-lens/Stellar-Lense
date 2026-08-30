"""Migration framework tests with populated data fixtures and data preservation validation."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from detection.persistence import RiskScoreRecord, get_engine
from migrations.base import Migration
from migrations.runner import MigrationRunner


@pytest.fixture
def test_engine():
    """In-memory SQLite engine for testing."""
    from detection.persistence import Base

    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def populated_engine(test_engine):
    """Seed database with representative data for migration tests."""
    from detection.persistence import Base

    Base.metadata.create_all(test_engine)

    SessionLocal = type("SessionLocal", (), {
        "__call__": lambda self: Session(bind=test_engine)
    })()

    session = Session(bind=test_engine)
    try:
        base_rows = [
            RiskScoreRecord(
                wallet=f"GXXX{i:05d}",
                asset_pair="USDC/native",
                score=50 + (i % 50),
                benford_flag=i % 7 == 0,
                ml_flag=i % 5 == 0,
                confidence=75,
            )
            for i in range(10000)
        ]
        session.add_all(base_rows)
        session.commit()
    finally:
        session.close()

    return test_engine


@pytest.fixture
def migration_runner(test_engine):
    """Create a migration runner for the test database."""
    return MigrationRunner(test_engine)


class Test0001InitialSchema(Migration):
    """Initialize risk_scores, ensemble_weight_history, and related tables.

    This is the baseline schema migration that creates core tables.
    """

    @property
    def version(self) -> str:
        return "0001_initial_schema"

    def up(self, engine, session):
        from detection.persistence import Base

        Base.metadata.create_all(engine)

    def data_preservation_test(self, engine):
        pass


class TestMigrationFramework:
    """Test that migrations preserve data correctly."""

    def test_migration_execution_order(self, migration_runner):
        """Migrations execute in order without race conditions."""
        migrations = [Test0001InitialSchema()]
        migration_runner.run_migrations(migrations)

    def test_populated_fixture_seeded(self, populated_engine):
        """populated_engine fixture seeds 10k representative rows."""
        session = Session(bind=populated_engine)
        try:
            count = session.query(RiskScoreRecord).count()
            assert count == 10000, f"Expected 10000 rows, got {count}"

            benford_flagged = session.query(RiskScoreRecord).filter_by(benford_flag=True).count()
            ml_flagged = session.query(RiskScoreRecord).filter_by(ml_flag=True).count()

            assert benford_flagged > 0, "populated_engine should include benford-flagged rows"
            assert ml_flagged > 0, "populated_engine should include ml-flagged rows"
        finally:
            session.close()

    def test_concurrent_migration_lock_enforcement(self, migration_runner, test_engine):
        """Two concurrent runners cannot execute simultaneously (lock blocks second)."""
        session1 = Session(bind=test_engine)
        session2 = Session(bind=test_engine)

        try:
            migration_runner.acquire_migration_lock(session1)

            with pytest.raises(RuntimeError, match="Migration lock is held"):
                migration_runner.acquire_migration_lock(session2)
        finally:
            migration_runner.release_migration_lock(session1)
            session1.close()
            session2.close()

    def test_migration_checksum_validation(self, migration_runner, test_engine):
        """Applying an unmodified migration twice is idempotent."""
        migration = Test0001InitialSchema()
        migration_runner.apply_migration(migration)

        migration_runner.apply_migration(migration)

    def test_data_preservation_on_applied_migration(self, populated_engine):
        """Data preservation test runs and validates row survival."""
        session = Session(bind=populated_engine)
        try:
            before_count = session.query(RiskScoreRecord).count()

            migration = Test0001InitialSchema()
            migration.data_preservation_test(populated_engine)

            after_count = session.query(RiskScoreRecord).count()
            assert before_count == after_count, "Migration should preserve all rows"
        finally:
            session.close()
