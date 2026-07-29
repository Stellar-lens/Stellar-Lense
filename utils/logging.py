"""Structured logging and correlation setup shared across the pipeline.

Usage:
    from utils.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Loaded %d trades", len(trades_df))

Correlation context is stored in :mod:`contextvars`, so it is isolated across
threads and asynchronous tasks while remaining available to every logger used
within a pipeline stage::

    with log_context(correlation_id="01J...", pipeline_stage="ingestion"):
        logger.info("Loaded trade")
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from config import config

_CONFIGURED = False
_CORRELATION_ID_HEADER = "x-correlation-id"
_PIPELINE_STAGE_HEADER = "x-pipeline-stage"
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_pipeline_stage: ContextVar[str | None] = ContextVar("pipeline_stage", default=None)
_context_fields: ContextVar[dict[str, Any]] = ContextVar("log_context_fields", default={})


def new_correlation_id() -> str:
    """Return a globally unique, log-friendly correlation identifier."""
    return uuid.uuid4().hex


def get_log_context() -> dict[str, Any]:
    """Return a copy of the context currently attached to log records."""
    context = dict(_context_fields.get())
    correlation_id = _correlation_id.get()
    pipeline_stage = _pipeline_stage.get()
    if correlation_id is not None:
        context["correlation_id"] = correlation_id
    if pipeline_stage is not None:
        context["pipeline_stage"] = pipeline_stage
    return context


@contextmanager
def log_context(
    *,
    correlation_id: str | None = None,
    pipeline_stage: str | None = None,
    **fields: Any,
) -> Iterator[str]:
    """Bind correlation metadata for all logs emitted inside the context.

    Nested contexts inherit unspecified values and restore their parent values
    on exit. The yielded value is the active correlation ID; when none is
    supplied or inherited, a new ID is generated.
    """
    active_correlation_id = correlation_id or _correlation_id.get() or new_correlation_id()
    correlation_token: Token[str | None] = _correlation_id.set(active_correlation_id)
    stage_token: Token[str | None] | None = None
    if pipeline_stage is not None:
        stage_token = _pipeline_stage.set(pipeline_stage)
    fields_token = _context_fields.set({**_context_fields.get(), **fields})
    try:
        yield active_correlation_id
    finally:
        _context_fields.reset(fields_token)
        if stage_token is not None:
            _pipeline_stage.reset(stage_token)
        _correlation_id.reset(correlation_token)


def correlation_headers(correlation_id: str | None = None) -> list[tuple[str, bytes]]:
    """Encode the active correlation context as transport-safe headers."""
    cid = correlation_id or _correlation_id.get() or new_correlation_id()
    headers = [(_CORRELATION_ID_HEADER, cid.encode("utf-8"))]
    stage = _pipeline_stage.get()
    if stage is not None:
        headers.append((_PIPELINE_STAGE_HEADER, stage.encode("utf-8")))
    return headers


def correlation_id_from_headers(
    headers: Mapping[str, str | bytes] | list[tuple[str, str | bytes]] | None,
) -> str | None:
    """Read a correlation ID from HTTP- or Kafka-style headers."""
    if not headers:
        return None
    items = headers.items() if isinstance(headers, Mapping) else headers
    for name, value in items:
        if name.lower() != _CORRELATION_ID_HEADER:
            continue
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)
    return None


class _CorrelationFilter(logging.Filter):
    """Inject the current correlation fields into every emitted log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_log_context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Logs must stay off stdout so callers can pipe a script's stdout
    # (e.g. JSON results) without status/info noise mixed in.
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_CorrelationFilter())

    if config.LOG_FORMAT == "json":
        try:
            from pythonjsonlogger import jsonlogger
            formatter = jsonlogger.JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s "
                "%(correlation_id)s %(pipeline_stage)s"
            )
        except ImportError:
            formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")

    handler.setFormatter(formatter)
    
    # Remove existing handlers to avoid duplicates
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for `name` (typically `__name__`)."""
    _configure()
    return logging.getLogger(name)


def set_level(level: str) -> None:
    """Override the root logger's verbosity, e.g. from a CLI --log-level flag."""
    _configure()
    logging.getLogger().setLevel(level.upper())
