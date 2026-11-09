"""Environment-driven CORS configuration for the StellarLense API.

The other variables this service reads (DB_PATH, DEMO_MODE,
STELLAR_NETWORK) are read where they're used, in api/storage.py; see
apps/api/.env.example for the full list.
"""

import os

_DEFAULT_DEV_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def cors_allowed_origins() -> list[str]:
    """Origins allowed to call this API from a browser (apps/web's domain(s)).

    Reads CORS_ALLOWED_ORIGINS as a comma-separated list. Falls back to the
    local Next.js dev server origins so `uvicorn api.main:app --reload`
    keeps working out of the box without a .env file. In a real deployment,
    set this to the actual deployed apps/web origin(s) — see
    apps/api/.env.example.
    """
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", _DEFAULT_DEV_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
