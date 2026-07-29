"""Tests for detection/artifact_compatibility.py and scripts/check_artifact_compatibility.py
(Issue #510)."""

import json

from detection.artifact_compatibility import (
    check_backward_compatibility,
    parse_version,
)
from scripts.check_artifact_compatibility import main as check_artifact_compatibility_main

BASE_METADATA = {
    "feature_schema_hash": "sha256:abc",
    "feature_columns": ["trade_count", "benford_score"],
    "ledgerlens_version": "0.2.0",
}
BASE_METRICS = {"rf": {"auc_roc": 0.90}}


def test_identical_artifacts_are_compatible():
    report = check_backward_compatibility(BASE_METADATA, dict(BASE_METADATA))
    assert report.compatible
    assert bool(report) is True
    assert not report.breaking


def test_removed_feature_column_is_breaking():
    new_metadata = dict(BASE_METADATA, feature_columns=["trade_count"])
    report = check_backward_compatibility(BASE_METADATA, new_metadata)
    assert not report.compatible
    assert any(i.field == "feature_columns" for i in report.breaking)


def test_added_feature_column_is_only_a_warning():
    new_metadata = dict(
        BASE_METADATA, feature_columns=["trade_count", "benford_score", "new_feature"]
    )
    report = check_backward_compatibility(BASE_METADATA, new_metadata)
    assert report.compatible
    assert any(i.field == "feature_columns" for i in report.warnings)


def test_missing_required_field_is_breaking():
    new_metadata = {"feature_columns": ["trade_count"]}
    report = check_backward_compatibility(BASE_METADATA, new_metadata)
    assert not report.compatible
    breaking_fields = {i.field for i in report.breaking}
    assert "feature_schema_hash" in breaking_fields
    assert "ledgerlens_version" in breaking_fields


def test_version_regression_is_breaking():
    new_metadata = dict(BASE_METADATA, ledgerlens_version="0.1.9")
    report = check_backward_compatibility(BASE_METADATA, new_metadata)
    assert not report.compatible
    assert any(i.field == "ledgerlens_version" for i in report.breaking)


def test_version_bump_is_fine():
    new_metadata = dict(BASE_METADATA, ledgerlens_version="0.3.0")
    report = check_backward_compatibility(BASE_METADATA, new_metadata)
    assert report.compatible


def test_metric_regression_within_budget_is_a_warning():
    new_metrics = {"rf": {"auc_roc": 0.885}}  # 0.015 drop, budget 0.02
    report = check_backward_compatibility(
        BASE_METADATA, dict(BASE_METADATA), BASE_METRICS, new_metrics
    )
    assert report.compatible
    assert any(i.field == "metrics.rf.auc_roc" for i in report.warnings)


def test_metric_regression_beyond_budget_is_breaking():
    new_metrics = {"rf": {"auc_roc": 0.80}}  # 0.10 drop
    report = check_backward_compatibility(
        BASE_METADATA, dict(BASE_METADATA), BASE_METRICS, new_metrics
    )
    assert not report.compatible
    assert any(i.field == "metrics.rf.auc_roc" for i in report.breaking)


def test_metric_improvement_raises_no_issue():
    new_metrics = {"rf": {"auc_roc": 0.95}}
    report = check_backward_compatibility(
        BASE_METADATA, dict(BASE_METADATA), BASE_METRICS, new_metrics
    )
    assert report.compatible
    assert not report.issues


def test_parse_version_handles_prerelease_suffix():
    assert parse_version("0.2.0") == (0, 2, 0)
    assert parse_version("1.10.2") > parse_version("1.9.9")
    assert parse_version("0.2.0-rc1") == (0, 2, 0)


def test_report_format_lists_all_issues():
    new_metadata = dict(BASE_METADATA, feature_columns=["trade_count"])
    report = check_backward_compatibility(BASE_METADATA, new_metadata)
    text = report.format()
    assert "INCOMPATIBLE" in text
    assert "BREAKING" in text


# ---------------------------------------------------------------------------
# CLI (scripts/check_artifact_compatibility.py)
# ---------------------------------------------------------------------------


def _write_artifact(tmp_dir, metadata=None, metrics=None):
    tmp_dir.mkdir(parents=True, exist_ok=True)
    if metadata is not None:
        (tmp_dir / "model_metadata.json").write_text(json.dumps(metadata))
    if metrics is not None:
        (tmp_dir / "metrics.json").write_text(json.dumps(metrics))


def test_cli_skips_when_no_baseline(tmp_path, capsys):
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    _write_artifact(candidate_dir, BASE_METADATA, BASE_METRICS)

    exit_code = check_artifact_compatibility_main(
        ["--baseline-dir", str(baseline_dir), "--candidate-dir", str(candidate_dir)]
    )

    assert exit_code == 0
    assert "skipping" in capsys.readouterr().out.lower()


def test_cli_fails_when_candidate_missing_metadata(tmp_path):
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    _write_artifact(baseline_dir, BASE_METADATA, BASE_METRICS)
    candidate_dir.mkdir()

    exit_code = check_artifact_compatibility_main(
        ["--baseline-dir", str(baseline_dir), "--candidate-dir", str(candidate_dir)]
    )

    assert exit_code == 2


def test_cli_exits_nonzero_on_incompatible_change(tmp_path):
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    _write_artifact(baseline_dir, BASE_METADATA, BASE_METRICS)
    _write_artifact(
        candidate_dir, dict(BASE_METADATA, feature_columns=["trade_count"]), BASE_METRICS
    )

    exit_code = check_artifact_compatibility_main(
        ["--baseline-dir", str(baseline_dir), "--candidate-dir", str(candidate_dir)]
    )

    assert exit_code == 1


def test_cli_exits_zero_on_compatible_change(tmp_path):
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    _write_artifact(baseline_dir, BASE_METADATA, BASE_METRICS)
    _write_artifact(candidate_dir, dict(BASE_METADATA), BASE_METRICS)

    exit_code = check_artifact_compatibility_main(
        ["--baseline-dir", str(baseline_dir), "--candidate-dir", str(candidate_dir)]
    )

    assert exit_code == 0
