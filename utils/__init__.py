"""Shared utilities used across ingestion and detection modules.

Public consumers outside this package should prefer the typed contracts in
``utils.boundaries`` (``CircuitBreakerPort``, ``RetryPolicyPort``,
``TracerFactoryPort``, ``FieldEncryptionPort``, ``StructuredLoggerFactoryPort``)
over importing concrete modules directly -- see ``utils/boundaries.py`` for
the rationale and ``scripts/check_service_boundaries.py`` for the CI gate
that keeps the contracts and implementations in sync.
"""

from utils.boundaries import (
    CircuitBreakerPort,
    FieldEncryptionPort,
    RetryPolicyPort,
    ServiceBoundaryError,
    ServiceRegistry,
    StructuredLoggerFactoryPort,
    TracerFactoryPort,
    registry,
    validate_service_boundaries,
)

__all__ = [
    "CircuitBreakerPort",
    "FieldEncryptionPort",
    "RetryPolicyPort",
    "ServiceBoundaryError",
    "ServiceRegistry",
    "StructuredLoggerFactoryPort",
    "TracerFactoryPort",
    "registry",
    "validate_service_boundaries",
]
