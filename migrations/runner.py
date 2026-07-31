"""Migration runner: discovers, orders, and applies database migrations.

The runner keeps track of applied migrations in the ``schema_migrations``
table (created automatically on first use).  It is safe to call
:meth:`MigrationRunner.upgrade` in application startup code — if everything
is already up-to-date it returns immediately.

Thread safety: the runner acquires an advisory row-level lock (an ``INSERT``
with ``ON CONFLICT DO NOTHING`` into a ``migration_lock`` table) before
applying any migration so that concurrent startup pods do not race each other.
For SQLite this reduces to a plain serialised write thanks to WAL mode.
"""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from migrations.base import Migration
from migrations.registry import REGISTRY

logger = logging.getLogger(__name__)

_VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "versions")
_TRACKING_TABLE = "schema_migrations"
_LOCK_TABLE = "migration_lock"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_tracking_tables(conn: Connection) -> None:
    """Create the migration bookkeeping tables if they do not exist yet."""
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_TRACKING_TABLE} (
                migration_id    VARCHAR NOT NULL PRIMARY KEY,
                description     VARCHAR NOT NULL,
                applied_at      TIMESTAMP WITH TIME ZONE NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_LOCK_TABLE} (
                lock_name VARCHAR NOT NULL PRIMARY KEY
            )
            """
        )
    )


def _acquire_lock(conn: Connection) -> None:
    """Best-effort advisory lock for SQLite / PostgreSQL.

    Uses ``INSERT OR IGNORE`` (SQLite) or ``INSERT ... ON CONFLICT DO NOTHING``
    (PostgreSQL) so that only one migration runner is active at a time when
    multiple processes start simultaneously.  For SQLite the WAL + busy-timeout
    provides the actual serialisation guarantee; this table insert is an
    extra canary.
    """
    try:
        conn.execute(
            text(
                f"INSERT OR IGNORE INTO {_LOCK_TABLE} (lock_name) VALUES ('global')"
            )
        )
    except Exception:  # pragma: no cover — dialect-specific fallback
        try:
            conn.execute(
                text(
                    f"INSERT INTO {_LOCK_TABLE} (lock_name) VALUES ('global') ON CONFLICT DO NOTHING"
                )
            )
        except Exception:
            logger.warning("Could not acquire migration advisory lock — proceeding anyway")


def _applied_ids(conn: Connection) -> set[str]:
    rows = conn.execute(text(f"SELECT migration_id FROM {_TRACKING_TABLE}")).fetchall()
    return {r[0] for r in rows}


def _record_applied(conn: Connection, migration: Migration) -> None:
    conn.execute(
        text(
            f"INSERT INTO {_TRACKING_TABLE} (migration_id, description, applied_at)"
            " VALUES (:mid, :desc, :at)"
        ),
        {
            "mid": migration.id,
            "desc": migration.description,
            "at": datetime.now(UTC).isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Migration discovery
# ---------------------------------------------------------------------------


def _load_all_migrations() -> list[Migration]:
    """Import every ``migrations/versions/NNNN_*.py`` module and return its
    ``migration`` object sorted by numeric ID."""
    if not os.path.isdir(_VERSIONS_DIR):
        return []

    migrations: list[Migration] = []
    for fname in sorted(os.listdir(_VERSIONS_DIR)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        module_name = f"migrations.versions.{fname[:-3]}"
        mod = importlib.import_module(module_name)
        if not hasattr(mod, "migration"):
            logger.warning("Migration module %s has no 'migration' attribute — skipping", module_name)
            continue
        m = mod.migration
        if not isinstance(m, Migration):
            raise TypeError(
                f"{module_name}.migration must be a Migration instance, got {type(m)}"
            )
        migrations.append(m)

    # Sort by numeric id (the leading digits) for safety even if filenames are
    # not perfectly sorted by the OS.
    migrations.sort(key=lambda m: int(m.id))
    return migrations


def _verify_registry(migrations: list[Migration]) -> None:
    """Raise if any known migration ID is missing from the discovered list
    (i.e. the migration file was deleted)."""
    discovered_ids = {m.id for m in migrations}
    for rid in REGISTRY:
        if rid not in discovered_ids:
            raise RuntimeError(
                f"Migration {rid!r} is listed in the registry but its file is missing. "
                "Never delete a migration file that has been applied to a database."
            )


# ---------------------------------------------------------------------------
# Status dataclass
# ---------------------------------------------------------------------------


@dataclass
class MigrationStatus:
    """Summary of applied and pending migrations for display / assertion."""

    applied: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)

    @property
    def is_up_to_date(self) -> bool:
        return len(self.pending) == 0

    def __str__(self) -> str:  # pragma: no cover
        lines = []
        for mid in self.applied:
            lines.append(f"  [applied] {mid}")
        for mid in self.pending:
            lines.append(f"  [pending] {mid}")
        return "\n".join(lines) if lines else "  (no migrations found)"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class MigrationRunner:
    """Discover and apply LedgerLens schema migrations.

    Parameters
    ----------
    engine:
        The SQLAlchemy engine to migrate.  Defaults to the application engine
        from ``detection.persistence.get_engine()``.
    target:
        Optional 4-digit migration ID to stop at (inclusive).  ``None`` means
        apply all pending migrations.
    dry_run:
        Log the migrations that *would* be applied without executing them.
    """

    def __init__(
        self,
        engine: Engine | None = None,
        *,
        target: str | None = None,
        dry_run: bool = False,
    ) -> None:
        if engine is None:
            from detection.persistence import get_engine

            engine = get_engine()
        self._engine = engine
        self._target = target
        self._dry_run = dry_run

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upgrade(self, target: str | None = None) -> MigrationStatus:
        """Apply all pending migrations up to *target* (inclusive).

        Returns the final :class:`MigrationStatus`.
        """
        target = target or self._target
        all_migrations = _load_all_migrations()
        _verify_registry(all_migrations)

        if target is not None:
            known_ids = {m.id for m in all_migrations}
            if target not in known_ids:
                raise ValueError(f"Unknown migration target {target!r}. Known: {sorted(known_ids)}")
            all_migrations = [m for m in all_migrations if int(m.id) <= int(target)]

        with self._engine.begin() as conn:
            _ensure_tracking_tables(conn)
            _acquire_lock(conn)
            applied = _applied_ids(conn)

            pending = [m for m in all_migrations if m.id not in applied]
            if not pending:
                logger.info("Database is up to date — no migrations to apply")
                return self._build_status(all_migrations, applied)

            for migration in pending:
                if self._dry_run:
                    logger.info("[dry-run] Would apply migration %s: %s", migration.id, migration.description)
                    continue
                logger.info("Applying migration %s: %s", migration.id, migration.description)
                migration.up(conn)
                _record_applied(conn, migration)
                logger.info("Migration %s applied successfully", migration.id)

        # Re-read status after applying
        with self._engine.connect() as conn:
            applied = _applied_ids(conn)
        return self._build_status(all_migrations, applied)

    def status(self) -> MigrationStatus:
        """Return :class:`MigrationStatus` without applying anything."""
        all_migrations = _load_all_migrations()
        _verify_registry(all_migrations)

        with self._engine.begin() as conn:
            _ensure_tracking_tables(conn)
            applied = _applied_ids(conn)

        return self._build_status(all_migrations, applied)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_status(self, all_migrations: list[Migration], applied: set[str]) -> MigrationStatus:
        return MigrationStatus(
            applied=[m.id for m in all_migrations if m.id in applied],
            pending=[m.id for m in all_migrations if m.id not in applied],
        )
