"""Validate the current environment against a runtime mode's config contract.

Runs the same checks each entry point (run_pipeline.py, api/app.py,
scripts/stream.py, ...) enforces at startup — see config/contracts.py — but
without starting the service. Useful in CI, in a pre-deploy check, or when
debugging "why won't this start" locally.

Usage::

    python -m scripts.check_env --mode api
    python -m scripts.check_env --mode pipeline_onchain
    python -m scripts.check_env --all
    python -m scripts.check_env --all --json
    python -m scripts.check_env --list-modes
"""

from __future__ import annotations

import argparse
import json
import sys

from config.contracts import RUNTIME_MODES, list_modes, validate_mode


def _print_modes_table(modes: list[dict[str, Any]]) -> None:
    col_w = max(len(m["mode"]) for m in modes)
    col_w = max(col_w, 4)
    header = f"{'MODE':<{col_w}}  {'REQUIRED VARIABLES'}"
    print(header)
    print("-" * len(header))
    for m in modes:
        req = ", ".join(m["required_attrs"]) if m["required_attrs"] else "(none)"
        cond = ", ".join(m["conditional_attrs"]) if m["conditional_attrs"] else ""
        suffix = f"  [if applicable: {cond}]" if cond else ""
        print(f"{m['mode']:<{col_w}}  {req}{suffix}")
        print(f"{'':<{col_w}}  ({m['description']})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate LedgerLens runtime-mode config contracts"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--mode", choices=sorted(RUNTIME_MODES), help="Validate a single runtime mode"
    )
    group.add_argument("--all", action="store_true", help="Validate every known runtime mode")
    group.add_argument(
        "--list-modes",
        action="store_true",
        help="List every registered mode and its required variables",
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args(argv)

    if args.list_modes:
        modes = list_modes()
        if args.json:
            print(json.dumps({"ok": True, "modes": modes}, indent=2))
        else:
            _print_modes_table(modes)
        return 0

    modes = sorted(RUNTIME_MODES) if args.all else [args.mode]
    results = []

    for mode in modes:
        try:
            validate_mode(mode)
        except OSError as exc:
            results.append({"mode": mode, "ok": False, "error": str(exc)})
        else:
            results.append({"mode": mode, "ok": True, "error": None})

    ok = all(r["ok"] for r in results)

    if args.json:
        print(json.dumps({"ok": ok, "results": results}, indent=2))
    else:
        for r in results:
            if r["ok"]:
                print(f"[OK]   {r['mode']}")
            else:
                print(f"[FAIL] {r['mode']}")
                for line in r["error"].splitlines():
                    print(f"       {line}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
