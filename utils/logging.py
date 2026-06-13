"""Structured logging setup shared across the pipeline.

Usage:
    from utils.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Loaded %d trades", len(trades_df))
"""

import logging
import os

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for `name` (typically `__name__`)."""
    _configure()
    return logging.getLogger(name)
