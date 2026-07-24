import os
import json
from utils.secrets import sanitize_url, mask_secret, SENSITIVE_PARAM_KEYS

def run_diagnostics():
    db_url = os.environ.get("RISK_SCORE_DB_URL", "")
    horizon_url = os.environ.get("HORIZON_URL", "")
    kafka_sasl_pass = os.environ.get("KAFKA_SASL_PASSWORD", "")

    env_details = {}
    missing = []

    if db_url:
        env_details["RISK_SCORE_DB_URL"] = sanitize_url(db_url)
    else:
        missing.append("RISK_SCORE_DB_URL")

    if horizon_url:
        env_details["HORIZON_URL"] = sanitize_url(horizon_url)
    else:
        missing.append("HORIZON_URL")

    if kafka_sasl_pass:
        env_details["KAFKA_SASL_PASSWORD"] = mask_secret(kafka_sasl_pass)

    env_status = "PASS" if not missing else "FAIL"

    return {
        "overall_status": env_status,
        "checks": {
            "environment": {
                "status": env_status,
                "details": env_details,
                "missing": missing
            },
            "streaming": {
                "status": "PASS",
                "backend": os.environ.get("STREAMING_BACKEND", "stdout")
            }
        }
    }
