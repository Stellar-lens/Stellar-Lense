"""Build and deploy stellar-lense-registry (and the mock-amm demo) to testnet.

    uv run --package stellar-lense-core --extra chain \
        python contracts/soroban/deploy/deploy_testnet.py [--with-mock-amm]

Steps:
  1. cargo build the contract(s) for wasm32 with the pinned toolchain
     (contracts/soroban/rust-toolchain.toml) and hash the Wasm.
  2. Load admin + publisher keys from --keys (default .secrets/testnet-keys.json,
     gitignored) or generate them and fund them with friendbot. Testnet only:
     the script refuses any other network passphrase.
  3. Upload the Wasm, create the contract, call initialize(admin,
     [publisher], threshold).
  4. Write deployments/testnet.json (contract ids, Wasm hashes, admin and
     signer *public* keys, tx hashes, git commit). Never writes secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from stellar_sdk import Keypair, Network, SorobanServer, StrKey, TransactionBuilder, scval
from stellar_sdk import xdr as stellar_xdr

ROOT = Path(__file__).resolve().parents[3]
SOROBAN = ROOT / "contracts" / "soroban"
sys.path.insert(0, str(ROOT / "packages" / "core"))

from pipeline.soroban import TESTNET_RPC, RegistryClient, SorobanError, submit  # noqa: E402

FRIENDBOT = "https://friendbot.stellar.org"


def build(package: str) -> Path:
    subprocess.run(
        ["cargo", "build", "--release", "--target", "wasm32-unknown-unknown", "-p", package],
        cwd=SOROBAN,
        check=True,
    )
    return SOROBAN / "target" / "wasm32-unknown-unknown" / "release" / f"{package.replace('-', '_')}.wasm"


def load_or_create_keys(path: Path) -> dict[str, Keypair]:
    if path.exists():
        data = json.loads(path.read_text())
        return {k: Keypair.from_secret(v) for k, v in data.items()}
    keys = {"admin": Keypair.random(), "publisher": Keypair.random()}
    for name, kp in keys.items():
        r = httpx.get(FRIENDBOT, params={"addr": kp.public_key}, timeout=60)
        if r.status_code != 200:
            raise SystemExit(f"friendbot failed for {name}: {r.text[:200]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v.secret for k, v in keys.items()}, indent=2))
    os.chmod(path, 0o600)
    print(f"generated and funded testnet keys -> {path} (keep it; it's gitignored)")
    return keys


def upload(server: SorobanServer, admin: Keypair, wasm: bytes) -> tuple[str, str]:
    account = server.load_account(admin.public_key)
    tx = (
        TransactionBuilder(account, Network.TESTNET_NETWORK_PASSPHRASE, base_fee=100_000)
        .append_upload_contract_wasm_op(wasm)
        .set_timeout(120)
        .build()
    )
    tx_hash = submit(server, tx, admin)
    return hashlib.sha256(wasm).hexdigest(), tx_hash


def create(server: SorobanServer, admin: Keypair, wasm_hash: str) -> tuple[str, str]:
    salt = os.urandom(32)
    account = server.load_account(admin.public_key)
    tx = (
        TransactionBuilder(account, Network.TESTNET_NETWORK_PASSPHRASE, base_fee=100_000)
        .append_create_contract_op(wasm_id=bytes.fromhex(wasm_hash), address=admin.public_key, salt=salt)
        .set_timeout(120)
        .build()
    )
    # The simulation returns the new contract's address; read it before sending.
    sim = server.simulate_transaction(tx)
    if sim.error:
        raise SorobanError(f"create simulation failed: {sim.error}")
    contract_id = scval.to_native(stellar_xdr.SCVal.from_xdr(sim.results[0].xdr))
    contract_id = contract_id.address if hasattr(contract_id, "address") else str(contract_id)
    tx_hash = submit(server, tx, admin)
    return contract_id, tx_hash


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rpc", default=TESTNET_RPC)
    parser.add_argument("--keys", type=Path, default=ROOT / ".secrets" / "testnet-keys.json")
    parser.add_argument("--threshold", type=int, default=70)
    parser.add_argument("--with-mock-amm", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "deployments" / "testnet.json")
    args = parser.parse_args(argv)

    server = SorobanServer(args.rpc)
    if server.get_network().passphrase != Network.TESTNET_NETWORK_PASSPHRASE:
        raise SystemExit("refusing to deploy: RPC is not Stellar testnet")
    keys = load_or_create_keys(args.keys)
    admin, publisher = keys["admin"], keys["publisher"]

    wasm_path = build("stellar-lense-registry")
    wasm_hash, upload_tx = upload(server, admin, wasm_path.read_bytes())
    contract_id, create_tx = create(server, admin, wasm_hash)
    registry = RegistryClient(contract_id, rpc_url=args.rpc)
    init_tx = registry.invoke(
        admin,
        "initialize",
        [
            scval.to_address(admin.public_key),
            scval.to_vec([scval.to_address(publisher.public_key)]),
            scval.to_uint32(args.threshold),
        ],
    )
    assert StrKey.is_valid_contract(contract_id)
    print(f"registry {contract_id} (wasm {wasm_hash}) version {registry.version()}")

    record = {
        "network": "testnet",
        "rpc_url": args.rpc,
        "network_passphrase": Network.TESTNET_NETWORK_PASSPHRASE,
        "deployed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_commit": git_commit(),
        "registry": {
            "contract_id": contract_id,
            "wasm_hash": wasm_hash,
            "wasm_size_bytes": wasm_path.stat().st_size,
            "admin": admin.public_key,
            "signers": [publisher.public_key],
            "threshold": args.threshold,
            "transactions": {"upload": upload_tx, "create": create_tx, "initialize": init_tx},
        },
    }

    if args.with_mock_amm:
        amm_wasm = build("mock-amm")
        amm_hash, amm_upload = upload(server, admin, amm_wasm.read_bytes())
        amm_id, amm_create = create(server, admin, amm_hash)
        amm_init = RegistryClient(amm_id, rpc_url=args.rpc).invoke(
            admin,
            "initialize",
            [scval.to_address(admin.public_key), scval.to_address(contract_id), scval.to_uint32(args.threshold), scval.to_uint64(2 * 86_400)],
        )
        record["mock_amm"] = {
            "contract_id": amm_id,
            "wasm_hash": amm_hash,
            "registry": contract_id,
            "max_score": args.threshold,
            "max_age_secs": 2 * 86_400,
            "transactions": {"upload": amm_upload, "create": amm_create, "initialize": amm_init},
        }
        print(f"mock-amm {amm_id} gated on {contract_id}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
