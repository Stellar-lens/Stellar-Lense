"""Environment-driven configuration for the StellarLense API.

This service has no database and doesn't call CryptoPanic/CoinDesk — those
are apps/web's concerns (its own Next.js API route proxies the news feed
server-side; see apps/web/.env.example). The only genuine runtime config
this API reads is CORS, so that's the only thing here. Deliberately not a
pydantic-settings model or similar framework: two os.environ reads don't
need one, and this codebase doesn't otherwise use that pattern.
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
