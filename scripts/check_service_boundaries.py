#!/usr/bin/env python
"""Validate that shared-utility implementations still satisfy their typed
service-boundary contracts (``utils/boundaries.py``).

This is the CI-facing entry point for the service-boundary capability: it
exercises every default binding registered in ``utils.boundaries.registry``
and reports, per port, whether the bound implementation still structurally
satisfies its ``Protocol``. Run it locally with::

    python scripts/check_service_boundaries.py

Exit codes:
    0  every binding conforms to its contract
    1  one or more bindings are missing or have drifted from their contract

On failure the output names the offending port and, where possible, the
missing attribute/method, plus a pointer to ``utils/boundaries.py`` so a
contributor knows exactly where to fix the drift.
"""

from __future__ import annotations

import sys

from utils.boundaries import describe_bindings, validate_service_boundaries


def main() -> int:
    diagnostics = validate_service_boundaries()

    print("Service boundary bindings:")
    print(describe_bindings())
    print()

    if diagnostics:
        print("Service boundary check FAILED:")
        for d in diagnostics:
            print(f"  - {d}")
        print()
        print(
            "Fix by either updating the concrete implementation to satisfy the "
            "Protocol in utils/boundaries.py, or updating the Protocol if the "
            "contract itself intentionally changed."
        )
        return 1

    print("Service boundary check passed: all bindings satisfy their contracts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
