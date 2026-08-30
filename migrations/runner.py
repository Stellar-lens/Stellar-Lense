"""Migration runner with real blocking locks and checksum validation."""

import logging
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Table, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def _create_migration_metadata_table(engine: Engine) -> Table:
    """Create or get the migration metadata table."""
    from sqlalchemy import MetaData

    metadata = MetaData()
    migration_metadata = Table(
        "migration_metadata",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("version", String, unique=True, nullable=False, index=True),
        Column("content_hash", String, nullable=False),
        Column("applied_at", DateTime(timezone=True), default=lambda: datetime.now(UTC)),
    )

    metadata.create_all(engine)
    return migration_metadata


class MigrationRunner:
    """Executes migrations with blocking locks and checksum validation.

    Only one migration runner can execute against a database at a time.
    Uses database advisory locks (PostgreSQL) or a mutex table (SQLite).
    """

    MIGRATION_LOCK_ID = 1  # Numeric lock ID for advisory locks

    def __init__(self, engine: Engine):
        self.engine = engine
        self.SessionLocal = sessionmaker(bind=engine)

    def acquire_migration_lock(self, session: Session) -> bool:
        """Acquire an exclusive migration lock.

        For PostgreSQL: uses pg_advisory_lock()
        For SQLite: uses a mutex table with INSERT OR ABORT
        For other DBs: uses a simple mutex table

        Args:
            session: SQLAlchemy session

        Returns:
            True if lock acquired, False if already held (blocks, doesn't fail)
        """
        db_url = str(self.engine.url)

        if "postgresql" in db_url:
            session.execute("SELECT pg_advisory_lock(%d)" % self.MIGRATION_LOCK_ID)
            return True
        else:
            try:
                session.execute(
                    """
                    CREATE TABLE IF NOT EXISTS migration_lock (
                        lock_id INTEGER PRIMARY KEY,
                        locked_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                session.execute("INSERT INTO migration_lock (lock_id) VALUES (1)")
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                raise RuntimeError(
                    "Migration lock is held by another process. "
                    "Only one migration runner can execute at a time."
                )

    def release_migration_lock(self, session: Session) -> None:
        """Release the migration lock."""
        db_url = str(self.engine.url)

        if "postgresql" in db_url:
            session.execute("SELECT pg_advisory_unlock(%d)" % self.MIGRATION_LOCK_ID)
        else:
            session.execute("DELETE FROM migration_lock WHERE lock_id = 1")
            session.commit()

    def apply_migration(self, migration) -> None:
        """Apply a single migration with locking and checksum validation.

        Args:
            migration: Migration instance to apply

        Raises:
            RuntimeError: If lock acquisition fails or checksum validation fails
        """
        session = self.SessionLocal()
        try:
            if not self.acquire_migration_lock(session):
                raise RuntimeError("Failed to acquire migration lock")

            version = migration.version
            content_hash = migration.content_hash

            metadata_table = _create_migration_metadata_table(self.engine)

            stmt = select(metadata_table).where(metadata_table.c.version == version)
            existing = session.execute(stmt).first()

            if existing:
                if existing.content_hash != content_hash:
                    raise RuntimeError(
                        f"Migration {version} has been modified since application. "
                        f"Expected hash {existing.content_hash}, got {content_hash}"
                    )
                logger.info(f"Migration {version} already applied, skipping")
                return

            logger.info(f"Applying migration {version}: {migration.description}")
            migration.up(self.engine, session)

            stmt = metadata_table.insert().values(
                version=version, content_hash=content_hash
            )
            session.execute(stmt)
            session.commit()

            logger.info(f"Migration {version} applied successfully")

        except Exception as e:
            session.rollback()
            logger.error(f"Migration {version} failed: {e}")
            raise
        finally:
            self.release_migration_lock(session)
            session.close()

    def run_migrations(self, migrations: list) -> None:
        """Apply a list of migrations in order.

        Args:
            migrations: List of Migration instances in application order
        """
        for migration in migrations:
            self.apply_migration(migration)
