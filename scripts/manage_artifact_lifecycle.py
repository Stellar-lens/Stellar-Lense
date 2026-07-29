"""CLI for the versioned model artifact lifecycle registry.

Complements ``scripts/publish_model_artifact.py`` (signing + transparency
log) and ``scripts/list_model_versions.py`` (transparency-log listing) with
operational lifecycle commands backed by ``detection.artifact_lifecycle``.

Usage:
    python -m scripts.manage_artifact_lifecycle register --name rf --artifact-path models/rf.joblib
    python -m scripts.manage_artifact_lifecycle validate --name rf --version <version>
    python -m scripts.manage_artifact_lifecycle promote --name rf --version <version>
    python -m scripts.manage_artifact_lifecycle rollback --name rf --reason "AUC regression"
    python -m scripts.manage_artifact_lifecycle status --name rf
    python -m scripts.manage_artifact_lifecycle verify --name rf --version <version>
"""

import argparse
import json
import sys

from detection.artifact_lifecycle import ArtifactLifecycleError, ModelArtifactRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-path", default="models/artifact_manifest.json")
    sub = parser.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register")
    p_register.add_argument("--name", required=True)
    p_register.add_argument("--artifact-path", required=True)
    p_register.add_argument("--metrics-json", default=None, help="JSON string of metrics")

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--name", required=True)
    p_validate.add_argument("--version", required=True)

    p_promote = sub.add_parser("promote")
    p_promote.add_argument("--name", required=True)
    p_promote.add_argument("--version", required=True)

    p_deprecate = sub.add_parser("deprecate")
    p_deprecate.add_argument("--name", required=True)
    p_deprecate.add_argument("--version", required=True)
    p_deprecate.add_argument("--reason", default=None)

    p_rollback = sub.add_parser("rollback")
    p_rollback.add_argument("--name", required=True)
    p_rollback.add_argument("--version", default=None)
    p_rollback.add_argument("--reason", default=None)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--name", required=True)
    p_verify.add_argument("--version", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("--name", required=True)

    args = parser.parse_args()
    registry = ModelArtifactRegistry(manifest_path=args.manifest_path)

    try:
        if args.command == "register":
            metrics = json.loads(args.metrics_json) if args.metrics_json else {}
            version = registry.register(args.name, args.artifact_path, metrics=metrics)
            print(f"Registered {args.name}:{version} (stage=staged)")
        elif args.command == "validate":
            registry.validate(args.name, args.version)
            print(f"{args.name}:{args.version} -> validated")
        elif args.command == "promote":
            registry.promote(args.name, args.version)
            print(f"{args.name}:{args.version} -> promoted (active)")
        elif args.command == "deprecate":
            registry.deprecate(args.name, args.version, reason=args.reason)
            print(f"{args.name}:{args.version} -> deprecated")
        elif args.command == "rollback":
            record = registry.rollback(args.name, args.version, reason=args.reason)
            print(f"Rolled back {args.name}:{record.version}; reactivated parent={record.parent_version}")
        elif args.command == "verify":
            registry.verify_integrity(args.name, args.version)
            print(f"{args.name}:{args.version} integrity OK")
        elif args.command == "status":
            versions = registry.list_versions(args.name)
            if not versions:
                print(f"No versions registered for {args.name}")
            for record in versions:
                marker = " <- active" if record.stage.value == "promoted" else ""
                print(f"  {record.version}  stage={record.stage.value}{marker}")
    except ArtifactLifecycleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
