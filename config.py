"""Central configuration loaded from environment variables / .env."""

import os

from dotenv import load_dotenv

load_dotenv()


def _parse_pairs(raw: str) -> list[tuple[str, str]]:
    pairs = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        code, _, issuer = entry.partition(":")
        pairs.append((code, issuer or "native"))
    return pairs


def _parse_int_list(raw: str) -> list[int]:
    return [int(v.strip()) for v in raw.split(",") if v.strip()]


class Config:
    HORIZON_URL: str = os.getenv("HORIZON_URL", "https://horizon.stellar.org")
    STELLAR_NETWORK: str = os.getenv("STELLAR_NETWORK", "PUBLIC")

    WATCHED_ASSET_PAIRS: list[tuple[str, str]] = _parse_pairs(os.getenv("WATCHED_ASSET_PAIRS", ""))

    BENFORD_WINDOWS_HOURS: list[int] = _parse_int_list(
        os.getenv("BENFORD_WINDOWS_HOURS", "1,4,24,168,720")
    )

    CROSS_PAIR_SYNCHRONY_WINDOW_SECONDS: int = int(
        os.getenv("CROSS_PAIR_SYNCHRONY_WINDOW_SECONDS", "30")
    )

    RISK_SCORE_FLAG_THRESHOLD: int = int(os.getenv("RISK_SCORE_FLAG_THRESHOLD", "70"))

    RISK_SCORE_DB_URL: str = os.getenv("RISK_SCORE_DB_URL", "sqlite:///ledgerlens.db")

    MODEL_DIR: str = os.getenv("MODEL_DIR", "./models")

    # ledgerlens-score Soroban contract
    SOROBAN_RPC_URL: str = os.getenv("SOROBAN_RPC_URL", "https://soroban-testnet.stellar.org")
    LEDGERLENS_CONTRACT_ID: str = os.getenv("LEDGERLENS_CONTRACT_ID", "")
    LEDGERLENS_SUBMITTER_SECRET: str = os.getenv("LEDGERLENS_SUBMITTER_SECRET", "")

    # Model integrity & BFT voting
    MODEL_SIGNING_PRIVATE_KEY_PATH: str = os.getenv("MODEL_SIGNING_PRIVATE_KEY_PATH", "")
    TRUSTED_SIGNING_KEY_FINGERPRINT: str = os.getenv("TRUSTED_SIGNING_KEY_FINGERPRINT", "")
    BFT_SCORE_DIVERGENCE_THRESHOLD: int = int(os.getenv("BFT_SCORE_DIVERGENCE_THRESHOLD", "30"))
    BFT_MIN_CONSENSUS: int = int(os.getenv("BFT_MIN_CONSENSUS", "2"))
    POISON_LABEL_RATIO_THRESHOLD: float = float(os.getenv("POISON_LABEL_RATIO_THRESHOLD", "0.15"))

    # Annotation integrity
    ANNOTATION_HMAC_SECRET: str = os.getenv("ANNOTATION_HMAC_SECRET", "")


config = Config()
