"""Read scores back from the testnet deployment (used by the nightly CI job).

    uv run --package stellar-lense-core --extra chain \
        python contracts/soroban/deploy/check_testnet.py [--max-age-hours 48]

Read-only: every call is a simulation, so no keys are needed. Fails if the
registry is unreachable or reports the wrong version, if no tracked pair
has a published aggregate, or if the newest aggregate is older than
--max-age-hours (which means the publisher has stopped). Testnet is
periodically reset by SDF; after a reset this fails until
deploy_testnet.py is re-run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "core"))

from pipeline.jobs import load_pairs  # noqa: E402
from pipeline.soroban import RegistryClient  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--deployment", type=Path, default=ROOT / "deployments" / "testnet.json")
    parser.add_argument("--max-age-hours", type=float, default=48)
    args = parser.parse_args(argv)

    deployment = json.loads(args.deployment.read_text())
    registry = RegistryClient(deployment["registry"]["contract_id"], rpc_url=deployment["rpc_url"])
    version = registry.version()
    print(f"registry {registry.contract_id} version {version}")
    if version != 2:
        print("unexpected registry version", file=sys.stderr)
        return 1

    found = []
    for pair in load_pairs().pairs:
        aggregate = registry.get_pair_score(pair.id)
        if aggregate:
            found.append((pair.id, aggregate))
            print(f"  {pair.id.split(':')[0]}…  avg={aggregate['average']} max={aggregate['max']} "
                  f"flagged={aggregate['flagged']}/{aggregate['total']} as_of={aggregate['as_of']}")
    if not found:
        print("no pair aggregates published on the registry", file=sys.stderr)
        return 1

    newest = max(a["as_of"] for _, a in found)
    age_hours = (time.time() - newest) / 3600
    print(f"{len(found)} pairs published; newest data is {age_hours:.1f}h old")
    if age_hours > args.max_age_hours:
        print(f"newest published data is older than {args.max_age_hours}h: is the publisher running?", file=sys.stderr)
        return 1

    if "mock_amm" in deployment:
        amm = RegistryClient(deployment["mock_amm"]["contract_id"], rpc_url=deployment["rpc_url"])
        print(f"mock-amm {amm.contract_id} reachable: config={amm.simulate('config', [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
