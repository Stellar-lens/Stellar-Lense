"""Base migration framework with data preservation and checksum validation."""

import hashlib
import inspect
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


class Migration(ABC):
    """Abstract base class for all database migrations.

    Each migration:
    - Has an up() method that applies the migration
    - Must include a data_preservation_test() that verifies data survives
    - Is immutable once applied (content hash is validated)
    - Supports only forward migrations (down/rollback via forward-fix migrations)
    """

    @property
    def version(self) -> str:
        """Migration version from class name (e.g., 0001_initial_schema)."""
        return self.__class__.__name__

    @property
    def description(self) -> str:
        """Human-readable migration description."""
        return self.__doc__ or "No description"

    @property
    def content_hash(self) -> str:
        """SHA256 hash of migration source code for integrity validation."""
        source = inspect.getsource(self.__class__)
        return hashlib.sha256(source.encode()).hexdigest()

    @abstractmethod
    def up(self, engine: Engine, session: Session) -> None:
        """Apply the migration to the database.

        Args:
            engine: SQLAlchemy engine
            session: SQLAlchemy session for the migration
        """
        pass

    @abstractmethod
    def data_preservation_test(self, engine: Engine) -> None:
        """Verify pre-existing data survives this migration.

        This test runs against a database seeded with representative data.
        It must assert that no rows are lost and transformations are correct.

        Args:
            engine: SQLAlchemy engine with pre-populated data

        Raises:
            AssertionError: If data preservation is violated
        """
        pass
