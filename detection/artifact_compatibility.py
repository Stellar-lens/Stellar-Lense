"""Backward compatibility validation for stored model artifacts (Issue #510).

Every training run writes ``metrics.json`` and ``model_metadata.json`` into a
model directory (see :func:`detection.model_training.save_training_artifacts`).
When a new artifact is about to replace a previously archived one (see
``scripts/list_model_versions.py`` and ``models/archive/``), this module
checks that the replacement does not silently break existing consumers:

- :class:`detection.model_inference.ModelInferenceEngine` relies on
  ``feature_schema_hash``/``feature_columns`` to detect drift at inference
  time — removing a feature column the running model still needs is a
  breaking change, not just drift.
- ``ledgerlens_version`` must not regress (an older artifact must not silently
  replace a newer one).
- Recorded metric values (e.g. ``auc_roc``) must not regress beyond an
  acceptable budget, mirroring the accuracy-degradation budget already
  enforced for quantized artifacts in ``tests/test_quantize_models.py``.

This mirrors the compatibility vocabulary already used for Avro schema
evolution in ``ingestion/avro_codec.py`` / ``data/schema_evolution.md``, but
applies it to trained-model artifacts instead of message schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["breaking", "warning"]

#: Metadata fields every artifact must declare for compatibility checking to
#: be meaningful. Missing any of these is always a breaking issue.
REQUIRED_METADATA_FIELDS = ("feature_schema_hash", "feature_columns", "ledgerlens_version")

DEFAULT_MAX_METRIC_DROP = 0.02
DEFAULT_METRIC_KEY = "auc_roc"


@dataclass(frozen=True)
class CompatibilityIssue:
    """A single compatibility finding."""

    severity: Severity
    field: str
    message: str


@dataclass
class CompatibilityReport:
    """Result of a backward compatibility check between two artifact versions."""

    issues: list[CompatibilityIssue] = field(default_factory=list)

    @property
    def breaking(self) -> list[CompatibilityIssue]:
        return [i for i in self.issues if i.severity == "breaking"]

    @property
    def warnings(self) -> list[CompatibilityIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def compatible(self) -> bool:
        """True if there are no breaking issues (warnings are allowed)."""
        return not self.breaking

    def __bool__(self) -> bool:
        return self.compatible

    def format(self) -> str:
        if not self.issues:
            return "Compatible: no issues found."
        lines = []
        for i in self.breaking:
            lines.append(f"  [BREAKING] {i.field}: {i.message}")
        for i in self.warnings:
            lines.append(f"  [warning]  {i.field}: {i.message}")
        status = "COMPATIBLE" if self.compatible else "INCOMPATIBLE"
        header = f"{status} — {len(self.breaking)} breaking, {len(self.warnings)} warning(s)"
        return "\n".join([header, *lines])


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a dotted version string (``"0.2.0"``) into a comparable int tuple.

    Non-numeric trailing components (e.g. ``"0.2.0-rc1"``) are truncated at
    the first non-numeric segment so pre-release suffixes don't raise.
    """
    parts: list[int] = []
    for segment in version.strip().split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def check_backward_compatibility(
    old_metadata: dict,
    new_metadata: dict,
    old_metrics: dict | None = None,
    new_metrics: dict | None = None,
    *,
    max_metric_drop: float = DEFAULT_MAX_METRIC_DROP,
    metric_key: str = DEFAULT_METRIC_KEY,
) -> CompatibilityReport:
    """Check whether *new_metadata*/*new_metrics* is backward compatible with
    the previously stored *old_metadata*/*old_metrics*.

    "Backward compatible" here means: anything that depended on the old
    artifact (inference code expecting certain feature columns, dashboards
    reading a monotonic version, downstream consumers of recorded metrics)
    keeps working after the new artifact replaces it.

    Args:
        old_metadata: Previously stored ``model_metadata.json`` contents.
        new_metadata: Candidate ``model_metadata.json`` contents.
        old_metrics: Previously stored ``metrics.json`` contents (optional).
        new_metrics: Candidate ``metrics.json`` contents (optional).
        max_metric_drop: Maximum allowed absolute regression in *metric_key*
            per model before it is treated as breaking.
        metric_key: Metric name to compare per-model (default ``"auc_roc"``).

    Returns:
        A :class:`CompatibilityReport` listing every finding. Use
        ``report.compatible`` (or ``bool(report)``) to gate a release.
    """
    issues: list[CompatibilityIssue] = []

    for required in REQUIRED_METADATA_FIELDS:
        if required not in new_metadata:
            issues.append(
                CompatibilityIssue(
                    "breaking",
                    required,
                    f"New artifact metadata is missing required field '{required}'.",
                )
            )

    old_columns = set(old_metadata.get("feature_columns") or [])
    new_columns = set(new_metadata.get("feature_columns") or [])
    removed_columns = old_columns - new_columns
    added_columns = new_columns - old_columns

    if removed_columns:
        issues.append(
            CompatibilityIssue(
                "breaking",
                "feature_columns",
                "Feature column(s) removed that existing consumers may depend on: "
                f"{sorted(removed_columns)}.",
            )
        )
    if added_columns:
        issues.append(
            CompatibilityIssue(
                "warning",
                "feature_columns",
                f"Feature column(s) added: {sorted(added_columns)}. "
                "Ensure ModelInferenceEngine callers supply these at inference time.",
            )
        )

    old_version = old_metadata.get("ledgerlens_version")
    new_version = new_metadata.get("ledgerlens_version")
    if old_version and new_version:
        if parse_version(new_version) < parse_version(old_version):
            issues.append(
                CompatibilityIssue(
                    "breaking",
                    "ledgerlens_version",
                    f"New artifact version {new_version!r} is older than the "
                    f"existing artifact version {old_version!r}.",
                )
            )

    if old_metrics and new_metrics:
        for model_name, old_model_metrics in old_metrics.items():
            if not isinstance(old_model_metrics, dict) or metric_key not in old_model_metrics:
                continue
            new_model_metrics = new_metrics.get(model_name)
            if not isinstance(new_model_metrics, dict) or metric_key not in new_model_metrics:
                issues.append(
                    CompatibilityIssue(
                        "warning",
                        f"metrics.{model_name}.{metric_key}",
                        f"Model '{model_name}' no longer reports '{metric_key}' in the new "
                        "artifact.",
                    )
                )
                continue

            old_value = float(old_model_metrics[metric_key])
            new_value = float(new_model_metrics[metric_key])
            drop = old_value - new_value
            if drop > max_metric_drop:
                issues.append(
                    CompatibilityIssue(
                        "breaking",
                        f"metrics.{model_name}.{metric_key}",
                        f"'{metric_key}' regressed from {old_value:.4f} to {new_value:.4f} "
                        f"(drop of {drop:.4f} exceeds the allowed {max_metric_drop:.4f}).",
                    )
                )
            elif drop > 0:
                issues.append(
                    CompatibilityIssue(
                        "warning",
                        f"metrics.{model_name}.{metric_key}",
                        f"'{metric_key}' regressed slightly from {old_value:.4f} to "
                        f"{new_value:.4f} (within the allowed {max_metric_drop:.4f} budget).",
                    )
                )

    return CompatibilityReport(issues=issues)
