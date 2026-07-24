import sys
import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger("ledgerlens.cli.diagnostics")

def check_env_vars() -> Dict[str, Any]:
    required_vars = ["RISK_SCORE_DB_URL", "HORIZON_URL"]
    results = {}
    missing = []
    for var in required_vars:
        val = os.getenv(var)
        results[var] = "CONFIGURED" if val else "MISSING"
        if not val:
            missing.append(var)
    return {
        "status": "PASS" if not missing else "FAIL",
        "details": results,
        "missing": missing
    }

def check_streaming_backend() -> Dict[str, Any]:
    backend = os.getenv("STREAMING_BACKEND", "stdout").lower()
    if backend == "kafka":
        kafka_url = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
        if not kafka_url:
            return {
                "status": "FAIL",
                "backend": backend,
                "error": "KAFKA_BOOTSTRAP_SERVERS variable missing for kafka backend."
            }
        return {"status": "PASS", "backend": backend, "broker": kafka_url}
    return {"status": "PASS", "backend": backend}

def run_diagnostics() -> Dict[str, Any]:
    env_res = check_env_vars()
    stream_res = check_streaming_backend()
    overall_status = "PASS" if (env_res["status"] == "PASS" and stream_res["status"] == "PASS") else "FAIL"
    
    report = {
        "overall_status": overall_status,
        "checks": {
            "environment": env_res,
            "streaming": stream_res
        }
    }
    return report
