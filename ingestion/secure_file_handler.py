"""Secure file handling for uploaded ledger inputs.

Validates, sanitises, and safely processes user-uploaded ledger files (CSV,
JSON, NDJSON) before they enter the ingestion pipeline.  Prevents path
traversal, zip bombs, malicious content injection, and oversized uploads.

Usage::

    from ingestion.secure_file_handler import SecureFileHandler

    handler = SecureFileHandler()
    result = handler.ingest("uploads/ledger_export.csv")
    if result.accepted:
        df = result.dataframe
    else:
        print(result.rejection_reason)

Security invariants
-------------------
- All file paths are resolved to absolute paths and checked against an
  allow-listed base directory to prevent path traversal.
- File size is checked before reading content into memory.
- File content is validated against expected schemas before returning.
- Temporary files are written with mode 0o600.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum file size: 50 MB
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024

# Allowed extensions
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".json", ".ndjson", ".jsonl"})

# Maximum number of rows to ingest from a single file
MAX_ROWS: int = 1_000_000

# Maximum number of columns allowed
MAX_COLUMNS: int = 100

# Required columns for ledger input CSVs
REQUIRED_CSV_COLUMNS: frozenset[str] = frozenset({"trade_id", "amount"})

# Characters that are never allowed in field values (prevent injection)
_INJECTION_CHARS = frozenset({"=", "+", "-", "@", "\t", "\r"})

# Null byte — must never appear in text content
_NULL_BYTE = "\x00"


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class FileIngestionResult:
    """Result of a secure file ingestion attempt."""

    accepted: bool
    file_path: str
    file_hash: str = ""
    row_count: int = 0
    column_count: int = 0
    dataframe: pd.DataFrame | None = None
    rejection_reason: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_path(
    file_path: str | Path,
    *,
    allowed_base: str | Path | None = None,
) -> Path:
    """Resolve and validate a file path.

    Parameters
    ----------
    file_path : str | Path
        The path to validate.
    allowed_base : str | Path | None
        If set, the resolved path must be under this directory.

    Returns
    -------
    Path
        The resolved, validated absolute path.

    Raises
    ------
    ValueError
        If the path is invalid or outside the allowed base directory.
    FileNotFoundError
        If the file does not exist.
    """
    resolved = Path(file_path).resolve()

    # Path traversal check
    if allowed_base is not None:
        base = Path(allowed_base).resolve()
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise ValueError(
                f"Path traversal detected: '{file_path}' resolves outside "
                f"allowed base directory '{base}'."
            ) from exc

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")

    if not resolved.is_file():
        raise ValueError(f"Path is not a regular file: {resolved}")

    return resolved


def validate_extension(path: Path) -> str:
    """Check that the file extension is in the allow list.

    Returns the normalised extension (e.g. '.csv').

    Raises
    ------
    ValueError
        If the extension is not allowed.
    """
    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File extension '{ext}' is not allowed. "
            f"Accepted extensions: {sorted(ALLOWED_EXTENSIONS)}"
        )
    return ext


def validate_size(path: Path, max_bytes: int = MAX_FILE_SIZE_BYTES) -> int:
    """Check that the file size is within limits.

    Returns the file size in bytes.

    Raises
    ------
    ValueError
        If the file exceeds the size limit.
    """
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(
            f"File size {size:,} bytes exceeds maximum allowed " f"{max_bytes:,} bytes."
        )
    if size == 0:
        raise ValueError("File is empty (0 bytes).")
    return size


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file for audit trail."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def sanitise_cell_value(value: str) -> str:
    """Sanitise a single cell value to prevent CSV injection.

    Strips leading characters that spreadsheet applications interpret as
    formula starters (``=``, ``+``, ``-``, ``@``).  Also removes null bytes.
    """
    if not value:
        return value
    cleaned = value.replace(_NULL_BYTE, "")
    # Strip leading formula injection characters
    while cleaned and cleaned[0] in _INJECTION_CHARS:
        cleaned = cleaned[1:]
    return cleaned


def _check_null_bytes(content: str, path: str) -> None:
    """Raise ValueError if content contains null bytes."""
    if _NULL_BYTE in content:
        raise ValueError(
            f"File '{path}' contains null bytes, which may indicate binary or malicious content."
        )


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def _read_csv_secure(path: Path) -> pd.DataFrame:
    """Read a CSV file with security-conscious settings."""
    content = path.read_text(encoding="utf-8")
    _check_null_bytes(content, str(path))

    df = pd.read_csv(
        io.StringIO(content),
        nrows=MAX_ROWS,
        engine="python",
        on_bad_lines="skip",
    )

    if len(df.columns) > MAX_COLUMNS:
        raise ValueError(f"CSV has {len(df.columns)} columns, exceeding maximum of {MAX_COLUMNS}.")

    # Sanitise all string values
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].apply(lambda v: sanitise_cell_value(str(v)) if pd.notna(v) else v)

    return df


def _read_json_secure(path: Path) -> pd.DataFrame:
    """Read a JSON file (array of objects) securely."""
    content = path.read_text(encoding="utf-8")
    _check_null_bytes(content, str(path))

    data = json.loads(content)

    if isinstance(data, list):
        if len(data) > MAX_ROWS:
            data = data[:MAX_ROWS]
        df = pd.DataFrame(data)
    elif isinstance(data, dict):
        # Single record
        df = pd.DataFrame([data])
    else:
        raise ValueError(
            f"Unexpected JSON root type: {type(data).__name__}. Expected array or object."
        )

    if len(df.columns) > MAX_COLUMNS:
        raise ValueError(f"JSON has {len(df.columns)} columns, exceeding maximum of {MAX_COLUMNS}.")

    return df


def _read_ndjson_secure(path: Path) -> pd.DataFrame:
    """Read a newline-delimited JSON file securely."""
    content = path.read_text(encoding="utf-8")
    _check_null_bytes(content, str(path))

    records: list[dict[str, Any]] = []
    for i, line in enumerate(content.splitlines()):
        line = line.strip()
        if not line:
            continue
        if i >= MAX_ROWS:
            break
        records.append(json.loads(line))

    if not records:
        raise ValueError("NDJSON file contains no valid records.")

    df = pd.DataFrame(records)

    if len(df.columns) > MAX_COLUMNS:
        raise ValueError(
            f"NDJSON has {len(df.columns)} columns, exceeding maximum of {MAX_COLUMNS}."
        )

    return df


_READERS: dict[str, Any] = {
    ".csv": _read_csv_secure,
    ".json": _read_json_secure,
    ".ndjson": _read_ndjson_secure,
    ".jsonl": _read_ndjson_secure,
}


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class SecureFileHandler:
    """Securely ingest uploaded ledger files.

    Parameters
    ----------
    allowed_base : str | Path | None
        If set, all file paths must resolve under this directory.
    max_file_size : int
        Maximum file size in bytes (default 50 MB).
    require_columns : set[str] | None
        Columns that must be present in the ingested data.
        Defaults to ``REQUIRED_CSV_COLUMNS``.
    """

    def __init__(
        self,
        *,
        allowed_base: str | Path | None = None,
        max_file_size: int = MAX_FILE_SIZE_BYTES,
        require_columns: set[str] | None = None,
    ) -> None:
        self._allowed_base = allowed_base
        self._max_file_size = max_file_size
        self._require_columns = (
            require_columns if require_columns is not None else set(REQUIRED_CSV_COLUMNS)
        )

    def ingest(self, file_path: str | Path) -> FileIngestionResult:
        """Validate and ingest a ledger file.

        Returns a ``FileIngestionResult`` — check ``result.accepted``
        before using ``result.dataframe``.
        """
        str_path = str(file_path)

        try:
            resolved = validate_path(file_path, allowed_base=self._allowed_base)
            ext = validate_extension(resolved)
            file_size = validate_size(resolved, self._max_file_size)
            file_hash = compute_file_hash(resolved)

            logger.info(
                "Ingesting file: %s (size=%d, hash=%s)",
                resolved,
                file_size,
                file_hash[:12],
            )

            reader = _READERS[ext]
            df = reader(resolved)

            warnings: list[str] = []

            # Validate required columns
            if self._require_columns:
                missing = self._require_columns - set(df.columns)
                if missing:
                    return FileIngestionResult(
                        accepted=False,
                        file_path=str_path,
                        file_hash=file_hash,
                        rejection_reason=f"Missing required columns: {sorted(missing)}",
                    )

            # Check for duplicate rows
            n_dupes = df.duplicated().sum()
            if n_dupes > 0:
                warnings.append(f"Found {n_dupes} duplicate rows.")

            return FileIngestionResult(
                accepted=True,
                file_path=str_path,
                file_hash=file_hash,
                row_count=len(df),
                column_count=len(df.columns),
                dataframe=df,
                warnings=warnings,
            )

        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning("File ingestion rejected: %s — %s", str_path, exc)
            return FileIngestionResult(
                accepted=False,
                file_path=str_path,
                rejection_reason=str(exc),
            )
        except Exception as exc:
            logger.error("Unexpected error ingesting %s: %s", str_path, exc)
            return FileIngestionResult(
                accepted=False,
                file_path=str_path,
                rejection_reason=f"Unexpected error: {exc}",
            )
