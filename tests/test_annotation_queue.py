"""Tests for detection/active_learning/annotation_queue.py."""

import json
import os

from detection.active_learning.annotation_queue import (
    _compute_hmac,
    add_annotation,
    export_labelled,
)


def _queue_path(tmp_path) -> str:
    return str(tmp_path / "annotation_queue.json")


def test_add_annotation_creates_queue_with_hmac(tmp_path):
    path = _queue_path(tmp_path)
    ann = add_annotation(path, "GABC", 1, "alice", "2026-06-20T00:00:00Z")

    assert os.path.exists(path)
    assert ann["annotation_hmac"] == _compute_hmac("GABC", 1, "alice", "2026-06-20T00:00:00Z")


def test_export_labelled_returns_valid_annotations(tmp_path):
    path = _queue_path(tmp_path)
    add_annotation(path, "GABC", 1, "alice", "2026-06-20T00:00:00Z")
    add_annotation(path, "GXYZ", 0, "bob", "2026-06-20T01:00:00Z")

    result = export_labelled(path)
    assert len(result) == 2


def test_export_labelled_rejects_tampered_label(tmp_path):
    path = _queue_path(tmp_path)
    add_annotation(path, "GABC", 1, "alice", "2026-06-20T00:00:00Z")

    # Tamper the label in the file
    with open(path) as f:
        queue = json.load(f)
    queue[0]["label"] = 0  # flip label without re-computing HMAC
    with open(path, "w") as f:
        json.dump(queue, f)

    result = export_labelled(path)
    assert len(result) == 0  # tampered annotation excluded


def test_export_labelled_logs_warning_for_invalid_hmac(tmp_path, caplog):
    import logging

    path = _queue_path(tmp_path)
    add_annotation(path, "GABC", 1, "alice", "2026-06-20T00:00:00Z")

    with open(path) as f:
        queue = json.load(f)
    queue[0]["annotation_hmac"] = "badhash"
    with open(path, "w") as f:
        json.dump(queue, f)

    with caplog.at_level(logging.WARNING):
        export_labelled(path)

    assert any("Invalid HMAC" in r.message for r in caplog.records)


def test_export_labelled_excludes_invalid_includes_valid(tmp_path):
    path = _queue_path(tmp_path)
    add_annotation(path, "GABC", 1, "alice", "2026-06-20T00:00:00Z")
    add_annotation(path, "GXYZ", 0, "bob", "2026-06-20T01:00:00Z")

    # Tamper only first annotation
    with open(path) as f:
        queue = json.load(f)
    queue[0]["wallet"] = "GTAMPERED"
    with open(path, "w") as f:
        json.dump(queue, f)

    result = export_labelled(path)
    assert len(result) == 1
    assert result[0]["wallet"] == "GXYZ"


def test_export_labelled_empty_when_no_file(tmp_path):
    result = export_labelled(str(tmp_path / "nonexistent.json"))
    assert result == []
