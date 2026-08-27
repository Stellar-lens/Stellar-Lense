"""Tests for scripts/manage_artifact_lifecycle.py --check-only mode."""

import json
import subprocess
from pathlib import Path


def test_check_only_mode_does_not_modify_manifest(tmp_path, capsys):
    """Test that --check-only prints planned actions without modifying the manifest."""
    # Create test artifacts
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    artifact_v1 = artifact_dir / "model_v1.joblib"
    artifact_v1.write_bytes(b"model-bytes-v1")

    artifact_v2 = artifact_dir / "model_v2.joblib"
    artifact_v2.write_bytes(b"model-bytes-v2")

    manifest_path = tmp_path / "artifact_manifest.json"

    # Register v1 and promote it
    subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "register", "--name", "test-model", "--artifact-path", str(artifact_v1),
        ],
        check=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    # Get the version from the manifest
    with open(manifest_path) as f:
        manifest = json.load(f)
    v1_version = list(manifest["test-model"].keys())[0]

    # Validate v1
    subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "validate", "--name", "test-model", "--version", v1_version,
        ],
        check=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    # Promote v1
    subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "promote", "--name", "test-model", "--version", v1_version,
        ],
        check=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    # Save manifest state before check-only operations
    with open(manifest_path) as f:
        manifest_before = json.load(f)

    # Register v2
    result = subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "register", "--name", "test-model", "--artifact-path", str(artifact_v2),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    # Get the version of v2
    with open(manifest_path) as f:
        manifest = json.load(f)
    versions = list(manifest["test-model"].keys())
    v2_version = [v for v in versions if v != v1_version][0]

    # Validate v2
    subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "validate", "--name", "test-model", "--version", v2_version,
        ],
        check=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    # Save manifest state before check-only promote
    with open(manifest_path) as f:
        manifest_before_promote = json.load(f)

    # Try to promote v2 in check-only mode
    result = subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "--check-only",
            "promote", "--name", "test-model", "--version", v2_version,
        ],
        capture_output=True,
        text=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    # Assert the manifest was not modified
    with open(manifest_path) as f:
        manifest_after = json.load(f)
    assert manifest_after == manifest_before_promote, "Manifest should not be modified in --check-only mode"

    # Assert the action was printed
    output = result.stdout
    assert "test-model" in output, "Should print the artifact name"
    assert v2_version in output, "Should print the version"
    assert "promote" in output.lower(), "Should indicate the promote action in the output"


def test_check_only_deprecate_no_changes(tmp_path):
    """Test that --check-only mode for deprecate doesn't modify the manifest."""
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    artifact = artifact_dir / "model.joblib"
    artifact.write_bytes(b"model-bytes")

    manifest_path = tmp_path / "artifact_manifest.json"

    # Register and promote an artifact
    subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "register", "--name", "model", "--artifact-path", str(artifact),
        ],
        check=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    with open(manifest_path) as f:
        manifest = json.load(f)
    version = list(manifest["model"].keys())[0]

    subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "validate", "--name", "model", "--version", version,
        ],
        check=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "promote", "--name", "model", "--version", version,
        ],
        check=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    # Save manifest state
    with open(manifest_path) as f:
        manifest_before = json.load(f)

    # Try to deprecate in check-only mode
    subprocess.run(
        [
            "python", "-m", "scripts.manage_artifact_lifecycle",
            "--manifest-path", str(manifest_path),
            "--check-only",
            "deprecate", "--name", "model", "--version", version,
            "--reason", "test deprecation",
        ],
        capture_output=True,
        text=True,
        cwd="/home/ajidokwu/Desktop/Drips/Fred/Ledgerlens-data",
    )

    # Assert manifest unchanged
    with open(manifest_path) as f:
        manifest_after = json.load(f)
    assert manifest_after == manifest_before, "Manifest should not be modified in --check-only mode"
