"""Structured logging setup shared across the pipeline.

Usage:
    from utils.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Loaded %d trades", len(trades_df))

Correlation IDs
---------------
When the ``CorrelationFilter`` is active (installed automatically), every log
record carries ``correlation_id``, ``stage``, ``pair_id``, and ``wallet``
attributes.  In JSON mode these are included in the output automatically.
In text mode they are appended as ``[correlation_id=<id> stage=<stage>]``.

Secret redaction
-----------------
All formatters route their final output through ``sanitize_text`` so secrets
(passwords, API keys, tokens) never reach log sinks.
"""

import logging
import os
import sys
from typing import Any

from config import config
from utils.secrets import sanitize_text

_CONFIGURED = False

# ── Correlation-enriched JSON formatter ──────────────────────────────────────

_CORRELATION_FIELDS = ("correlation_id", "stage", "pair_id", "wallet")


class SecretsRedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return sanitize_text(original)


class CorrelationJsonFormatter:
    """JSON formatter that includes correlation fields when present.

    Falls back to the standard ``pythonjsonlogger`` if the filter has not
    been installed (i.e. the record lacks correlation attributes).
    """

    def __init__(self, base_formatter: Any) -> None:
        self._base = base_formatter

    def format(self, record: logging.LogRecord) -> str:
        for field_name in _CORRELATION_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                setattr(record, field_name, value)
        return sanitize_text(self._base.format(record))


class CorrelationTextFormatter(logging.Formatter):
    """Text formatter that appends correlation fields to the log line."""

    _CORR_FMT = "[correlation_id={cid} stage={stage}]"

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
    ) -> None:
        super().__init__(fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        cid = getattr(record, "correlation_id", None)
        stage = getattr(record, "stage", None)
        if cid or stage:
            parts = []
            if cid:
                parts.append(f"correlation_id={cid}")
            if stage:
                parts.append(f"stage={stage}")
            pair_id = getattr(record, "pair_id", None)
            if pair_id:
                parts.append(f"pair_id={pair_id}")
            wallet = getattr(record, "wallet", None)
            if wallet:
                # Truncate wallet for readability in text mode
                short = wallet[:8] + "..." if len(wallet) > 11 else wallet
                parts.append(f"wallet={short}")
            base = f"{base} [{' '.join(parts)}]"
        return sanitize_text(base)


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Install the correlation filter on the root logger so every handler
    # receives correlation-enriched records.
    from utils.correlation import CorrelationFilter

    corr_filter = CorrelationFilter()
    root_logger.addFilter(corr_filter)

    # Logs must stay off stdout so callers can pipe a script's stdout
    # (e.g. JSON results) without status/info noise mixed in.
    handler = logging.StreamHandler(sys.stderr)

    if config.LOG_FORMAT == "json":
        try:
            from pythonjsonlogger import jsonlogger

            base_formatter = jsonlogger.JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s"
            )
            formatter = CorrelationJsonFormatter(base_formatter)
        except ImportError:
            formatter = CorrelationTextFormatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
    else:
        formatter = CorrelationTextFormatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

    handler.setFormatter(formatter)
    handler.addFilter(corr_filter)

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


def setup_logger(name: str = "ledgerlens", level: int = logging.INFO) -> logging.Logger:
    """Standalone logger with secret redaction, independent of the root config."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = SecretsRedactingFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
