"""Typed, machine-readable exceptions for ingestion boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar


class IngestionError(Exception):
    """Base class for failures raised by the ingestion subsystem.

    Attributes are intentionally stable so callers can make retry and routing
    decisions without parsing human-readable messages.
    """

    error_code: ClassVar[str] = "ingestion_error"
    default_retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        *,
        source: str | None = None,
        operation: str | None = None,
        retryable: bool | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.source = source
        self.operation = operation
        self.retryable = self.default_retryable if retryable is None else retryable
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        """Return a structured representation suitable for logs and DLQs."""
        payload: dict[str, Any] = {
            "error_code": self.error_code,
            "error_type": type(self).__name__,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.source is not None:
            payload["source"] = self.source
        if self.operation is not None:
            payload["operation"] = self.operation
        if self.details:
            payload["details"] = dict(self.details)
        return payload

    @classmethod
    def from_exception(
        cls,
        error: BaseException,
        *,
        source: str | None = None,
        operation: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> "IngestionError":
        """Create a typed wrapper while retaining the original exception cause."""
        wrapped = cls(
            str(error),
            source=source,
            operation=operation,
            details=details,
        )
        wrapped.__cause__ = error
        return wrapped


class IngestionTransportError(IngestionError, RuntimeError):
    """A network or broker failure that is normally safe to retry."""

    error_code = "ingestion_transport_error"
    default_retryable = True


class IngestionRateLimitError(IngestionTransportError):
    """A remote source rejected requests because its rate limit was exhausted."""

    error_code = "ingestion_rate_limit_exceeded"


class IngestionNotFoundError(IngestionError):
    """The requested upstream ingestion resource does not exist."""

    error_code = "ingestion_resource_not_found"


class IngestionValidationError(IngestionError, ValueError):
    """Base class for input that cannot enter the ingestion pipeline."""

    error_code = "ingestion_validation_error"


class RecordValidationError(IngestionValidationError):
    """A source record has missing, malformed, or invalid fields."""

    error_code = "ingestion_record_invalid"


class SchemaValidationError(IngestionValidationError):
    """A record does not conform to the configured serialization schema."""

    error_code = "ingestion_schema_invalid"


class SchemaDecodeError(IngestionValidationError):
    """A serialized payload cannot be decoded with the configured schema."""

    error_code = "ingestion_payload_decode_failed"
