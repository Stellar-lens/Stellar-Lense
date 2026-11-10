"""Minimal Soroban client for the stellar-lense-registry contract.

Used by the publisher (`pipeline.publish`), the testnet deploy script
(contracts/soroban/deploy/deploy_testnet.py) and the nightly read-back
check. Requires the ``[chain]`` extra (stellar-sdk).

Reads are simulations: no key, no fee, nothing submitted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from stellar_sdk import Keypair, Network, SorobanServer, TransactionBuilder, scval
from stellar_sdk import xdr as stellar_xdr
from stellar_sdk.exceptions import PrepareTransactionException
from stellar_sdk.soroban_rpc import GetTransactionStatus, SendTransactionStatus

TESTNET_RPC = "https://soroban-testnet.stellar.org"
METHODS = {"heuristic": 0, "ml": 1}
DECISIONS = {0: "allow", 1: "high_risk", 2: "no_score", 3: "stale"}
# Any funded account works as the source of a read-only simulation; the
# simulation never needs its signature. This is SDF's testnet friendbot.
_SIMULATION_SOURCE = "GAIH3ULLFQ4DGSECF2AR555KZ4KNDGEKN4AFI4SU2M7B43MGK3QJZNSR"


class SorobanError(RuntimeError):
    pass


@dataclass
class RegistryClient:
    contract_id: str
    rpc_url: str = TESTNET_RPC
    network_passphrase: str = Network.TESTNET_NETWORK_PASSPHRASE
    base_fee: int = 100_000

    def __post_init__(self) -> None:
        self.server = SorobanServer(self.rpc_url)

    # ── transport ────────────────────────────────────────────────────────────

    def _builder(self, source: str):
        account = self.server.load_account(source)
        return TransactionBuilder(account, self.network_passphrase, base_fee=self.base_fee)

    def simulate(self, function: str, args: list[stellar_xdr.SCVal], source: str | None = None) -> Any:
        tx = (
            self._builder(source or _SIMULATION_SOURCE)
            .append_invoke_contract_function_op(self.contract_id, function, args)
            .set_timeout(60)
            .build()
        )
        sim = self.server.simulate_transaction(tx)
        if sim.error:
            raise SorobanError(f"{function} simulation failed: {sim.error}")
        return scval.to_native(stellar_xdr.SCVal.from_xdr(sim.results[0].xdr))

    def invoke(self, signer: Keypair, function: str, args: list[stellar_xdr.SCVal]) -> str:
        """Submit a contract call signed by `signer`; returns the tx hash."""
        tx = (
            self._builder(signer.public_key)
            .append_invoke_contract_function_op(self.contract_id, function, args)
            .set_timeout(120)
            .build()
        )
        return submit(self.server, tx, signer)

    # ── registry API ─────────────────────────────────────────────────────────

    def submit_scores(self, signer: Keypair, rows: list[dict]) -> str:
        """rows: dicts with wallet, pair, score, confidence, method, as_of."""
        vec = scval.to_vec(
            [
                scval.to_struct(
                    {
                        "as_of": scval.to_uint64(int(r["as_of"])),
                        "confidence": scval.to_uint32(int(r["confidence"])),
                        "method": scval.to_uint32(METHODS[r["method"]]),
                        "pair": scval.to_string(r["pair"]),
                        "score": scval.to_uint32(int(r["score"])),
                        "wallet": scval.to_address(r["wallet"]),
                    }
                )
                for r in rows
            ]
        )
        return self.invoke(signer, "submit_scores", [scval.to_address(signer.public_key), vec])

    def submit_pair_score(self, signer: Keypair, pair: str, average: int, max_: int, flagged: int, total: int, as_of: int) -> str:
        return self.invoke(
            signer,
            "submit_pair_score",
            [
                scval.to_address(signer.public_key),
                scval.to_string(pair),
                scval.to_uint32(average),
                scval.to_uint32(max_),
                scval.to_uint32(flagged),
                scval.to_uint32(total),
                scval.to_uint64(as_of),
            ],
        )

    def get_score(self, wallet: str, pair: str) -> dict | None:
        return self.simulate("get_score", [scval.to_address(wallet), scval.to_string(pair)])

    def get_pair_score(self, pair: str) -> dict | None:
        return self.simulate("get_pair_score", [scval.to_string(pair)])

    def check(self, wallet: str, pair: str, max_score: int, max_age_secs: int) -> str:
        code = self.simulate(
            "check",
            [
                scval.to_address(wallet),
                scval.to_string(pair),
                scval.to_uint32(max_score),
                scval.to_uint64(max_age_secs),
            ],
        )
        return DECISIONS[int(code)]

    def version(self) -> int:
        return int(self.simulate("version", []))


def submit(server: SorobanServer, tx, signer: Keypair, timeout: float = 90.0) -> str:
    """Prepare (simulate + attach resources/auth), sign, send and wait."""
    try:
        prepared = server.prepare_transaction(tx)
    except PrepareTransactionException as exc:
        raise SorobanError(f"simulation failed: {exc.simulate_transaction_response.error}") from exc
    prepared.sign(signer)
    sent = server.send_transaction(prepared)
    if sent.status == SendTransactionStatus.ERROR:
        raise SorobanError(f"send failed: {sent.error_result_xdr}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = server.get_transaction(sent.hash)
        if result.status == GetTransactionStatus.SUCCESS:
            return sent.hash
        if result.status == GetTransactionStatus.FAILED:
            raise SorobanError(f"transaction {sent.hash} failed: {result.result_xdr}")
        time.sleep(2)
    raise SorobanError(f"transaction {sent.hash} not confirmed within {timeout}s")
