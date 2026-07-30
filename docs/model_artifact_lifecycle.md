# Versioned Model Artifact Lifecycle

## Why

Model artifacts under `models/` previously had two disconnected mechanisms:

- `scripts/publish_model_artifact.py` signs an artifact and appends its hash
  to the append-only `TransparencyLog` (see `detection/persistence.py`).
- `scripts/list_model_versions.py` reads that log back out.

Neither tracked *operational state*: which version is currently serving
traffic, which versions were staged but never promoted, or why a version
was rolled back. Answering "what's live right now, and what was live before
the last rollback" required reconstructing it from the transparency log by
hand.

## What this adds

`detection/artifact_lifecycle.py` introduces a small, file-backed registry
(`ModelArtifactRegistry`) with a typed `ArtifactRecord` contract and an
explicit state machine:

```
STAGED -> VALIDATED -> PROMOTED -> DEPRECATED
                           |
                           v
                      ROLLED_BACK -> STAGED (re-registration)
```

Illegal transitions (e.g. `STAGED -> PROMOTED`, skipping validation) raise
`InvalidTransitionError` with the current stage and the allowed next stages
in the message. `promote()` automatically demotes any previously-promoted
version of the same artifact family to `DEPRECATED`, so `get_active()`
always resolves to exactly one version. `rollback()` reactivates the parent
version that was active before the rolled-back one was promoted.

Every record stores the artifact's `sha256` at registration time;
`verify_integrity()` re-hashes the on-disk file and raises
`IntegrityCheckError` (with expected vs. actual hash) if it no longer
matches — this catches artifacts that were modified or replaced outside the
registry after being registered.

The manifest (`models/artifact_manifest.json` by default) is written with a
temp-file-plus-`os.replace` pattern so a crash mid-write cannot corrupt it.

## Contract surface

| Method | Purpose |
|---|---|
| `register(name, artifact_path, metrics, tags)` | Hash + record a new artifact in `STAGED` |
| `validate(name, version)` | `STAGED -> VALIDATED` |
| `promote(name, version)` | `VALIDATED -> PROMOTED`, demotes prior active version |
| `deprecate(name, version, reason)` | Retire a version |
| `rollback(name, version=None, reason=None)` | Roll back active (or given) version, reactivate parent |
| `verify_integrity(name, version)` | Re-hash and compare against manifest |
| `get_active(name)` | Currently promoted version, or raises `ArtifactNotFoundError` |
| `list_versions(name)` / `list_names()` | Enumeration for tooling/CLI |

## Developer commands

```
python -m scripts.manage_artifact_lifecycle register --name rf --artifact-path models/rf.joblib
python -m scripts.manage_artifact_lifecycle validate  --name rf --version <version>
python -m scripts.manage_artifact_lifecycle promote   --name rf --version <version>
python -m scripts.manage_artifact_lifecycle status     --name rf
python -m scripts.manage_artifact_lifecycle rollback   --name rf --reason "AUC regression on canary"
python -m scripts.manage_artifact_lifecycle verify     --name rf --version <version>
```

Tests: `tests/test_artifact_lifecycle.py` (happy path, illegal transitions,
promotion supersession, rollback/reactivation, tamper detection via
`verify_integrity`, and manifest persistence across process instances).
Run with `pytest tests/test_artifact_lifecycle.py -v`.

## Design tradeoffs

- **JSON manifest instead of a DB table.** Keeps this dependency-free and
  inspectable/editable in an incident, matching the existing SQLite/JSON
  mix already used by `TransparencyLog` and `models/metrics.json`. Tradeoff:
  no concurrent-writer locking; single-writer (CI/release process) is the
  assumed usage pattern, same as the existing `metrics.json` update in
  `publish_model_artifact.py`.
- **Separate from `TransparencyLog`.** The transparency log is a
  security/audit primitive (signed, append-only, tamper-evident). The
  lifecycle registry is an operational primitive (mutable state, "what's
  active now"). Conflating them would force the audit log to support
  mutation, weakening its guarantees.
- **Follow-up work:** wiring `promote()`/`rollback()` into
  `scripts/publish_model_artifact.py` and the drift-triggered retraining
  path (`scripts/retrain_if_drifted.py`) so lifecycle transitions happen
  automatically on the existing publish/retrain flows, rather than only via
  the new CLI.
