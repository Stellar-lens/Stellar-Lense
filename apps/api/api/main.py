"""FastAPI entry point for the StellarLense public REST API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import alerts, assets, scores

app = FastAPI(
    title="StellarLense API",
    description=(
        "Hybrid on-chain fraud detection for the Stellar DEX. "
        "Exposes StellarLense Risk Scores, alerts, and asset risk rankings."
    ),
    version="0.1.0",
)

# Public read-only API consumed directly from the browser by apps/web (and
# any other dashboard) — no cookies/auth headers involved, so a permissive
# origin list is fine here. Tighten this once apps/web's deployed origin is
# known instead of local dev ports.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(scores.router)
app.include_router(alerts.router)
app.include_router(assets.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
